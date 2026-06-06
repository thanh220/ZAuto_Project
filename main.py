package org.zauto;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.SslErrorHandler;
import android.net.http.SslError;
import android.widget.FrameLayout;
import android.view.ViewGroup;
import android.view.View;
import android.util.Log;
import java.lang.ref.WeakReference;
import java.util.concurrent.ConcurrentLinkedQueue;
import android.speech.tts.TextToSpeech;
import java.util.Locale;

public class ZaloWebManager {

    public static WebView hiddenWebView;
    public static FrameLayout webLayout;
    private static final String TAG = "ZAutoWebManager";

    private static Handler watchdogHandler;
    private static Runnable watchdogRunnable;
    public static long lastHeartbeat = System.currentTimeMillis();

    private static long lastReloadTime = 0;
    private static int reloadCountWindow = 0;
    private static long firstReloadInWindow = 0;

    private static WeakReference<Activity> activityRef;

    private static final ConcurrentLinkedQueue<Runnable> replyQueue = new ConcurrentLinkedQueue<>();
    private static boolean isSending = false;

    // =========================================================
    // ỐNG DẪN RAM SIÊU TỐC (BYPASS ANDROID 14 BROADCAST BAN)
    // =========================================================
    public static final ConcurrentLinkedQueue<String> pythonMsgQueue = new ConcurrentLinkedQueue<>();
    public static TextToSpeech tts;
	// =========================================================
    // HÀM ÉP TỈNH NGỦ TỪ PYTHON GỌI XUỐNG
    // =========================================================
    public static void forceWakeup() {
        safeEvaluateJs(
            "try { " +
            "   if(window.scanConvItem) { document.querySelectorAll('.msg-item').forEach(window.scanConvItem); } " +
            "   document.body.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, clientX: 100, clientY: 100}));" +
            "} catch(e) {}"
        );
    }
    // =========================================================
    // REPLY QUEUE
    // =========================================================
    private static void processReplyQueue() {
        if (isSending || replyQueue.isEmpty()) return;
        isSending = true;
        Runnable task = replyQueue.poll();
        if (task != null) {
            task.run();
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                isSending = false;
                processReplyQueue();
            }, 2500);
        } else {
            isSending = false;
        }
    }

    private static String escapeJs(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "");
    }

    private static void safeEvaluateJs(String js) {
        if (hiddenWebView != null && hiddenWebView.getParent() != null) {
            hiddenWebView.post(() -> hiddenWebView.evaluateJavascript(js, null));
        }
    }

    // =========================================================
    // SAFE RELOAD 
    // =========================================================
    public static void safeReload() {
        long now = System.currentTimeMillis();
        if (now - firstReloadInWindow > 60000) {
            reloadCountWindow = 0;
            firstReloadInWindow = now;
        }
        if (reloadCountWindow >= 3) {
            Log.e(TAG, "ANTI-LOOP: Blocked too many reloads!");
            return;
        }
        if (now - lastReloadTime > 15000) {
            Log.w(TAG, "PERFORMING SAFE RELOAD...");
            reloadCountWindow++;
            if (hiddenWebView != null) {
                hiddenWebView.post(() -> hiddenWebView.reload());
            }
            lastReloadTime = now;
        }
    }

    // =========================================================================
    // NÂNG CẤP ĐỘNG CƠ: HYBRID VISION-API AUTOMATION ENGINE (TẦNG 1 & TẦNG 3)
    // =========================================================================
    // =========================================================================
    // ĐỘNG CƠ CHỐT CUỐC V5.0 - IRON FIST ENGINE
    // Đảm bảo 100% đè tin gửi kèm (quote) dù text hay voice, dài hay ngắn
    // Luồng: API Webpack → Click Đúp Siêu Mạnh (4 chiến lược) → Enter fallback
    // =========================================================================
    public static void sendReplyToSpecificMessage(
            final Activity activity,
            final String conversationId,
            final String msgId,
            final String text,
            final String msgTextToFind,
            final String sentTime) {

        Activity safeActivity = activityRef != null ? activityRef.get() : activity;
        if (safeActivity == null || hiddenWebView == null) return;

        replyQueue.add(() -> safeActivity.runOnUiThread(() -> {
            try {
                String safeReply      = escapeJs(text);
                String safeSearch     = escapeJs(msgTextToFind != null ? msgTextToFind : "");
                String safeMsgId      = escapeJs(msgId != null ? msgId : "");
                String safeTime       = escapeJs(sentTime != null ? sentTime : "");
                String safeConvId     = escapeJs(conversationId != null ? conversationId : "");

                String jsCode =
                "(function() { try {" +

                // ─────────────────────────────────────────────────────────────
                // BIẾN TOÀN CỤC TRONG CLOSURE
                // ─────────────────────────────────────────────────────────────
                "var _convId      = '" + safeConvId + "';" +
                "var _reply       = '" + safeReply  + "';" +
                "var _search      = '" + safeSearch + "';" +
                "var _targetId    = '" + safeMsgId  + "';" +
                "var _sentTime    = '" + safeTime   + "';" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 0: KHÁM PHÁ WEBPACK API (GIỮ NGUYÊN TỪ BẢN CŨ)
                // ─────────────────────────────────────────────────────────────
                "function _discoverApi() {" +
				"   if (window.zMessenger && typeof window.zMessenger.sendMessage==='function') return true;" +

				// ── DUCK TYPING helper: nhận dạng đúng object API của Zalo ──────────
				"   var _isApi = function(obj) {" +
				"       if (!obj || typeof obj !== 'object') return false;" +
				// Zalo bắt buộc phải có sendMessage + (sendMsg HOẶC sendTextMessage)
				"       return typeof obj.sendMessage==='function' && " +
				"              (typeof obj.sendMsg==='function' || typeof obj.sendTextMessage==='function');" +
				"   };" +
				"   var _deepFind = function(obj) {" +
				"       if (_isApi(obj)) { window.zMessenger=obj; return true; }" +
				"       if (!obj || typeof obj!=='object') return false;" +
				"       var keys=Object.keys(obj);" +
				"       for(var i=0;i<keys.length;i++){" +
				"           var c=obj[keys[i]];" +
				"           if(c && typeof c==='object' && _isApi(c)){window.zMessenger=c;return true;}" +
				"       }" +
				"       return false;" +
				"   };" +

				// ── TẦNG 1: WEBPACK CACHE DUMP — Vét cạn RAM module đã load ─────────
				// Kỹ thuật này bất tử trước obfuscation vì không dùng tên biến
				"   try {" +
				"       var wreq = window.__webpack_require__ || window.webpackRequire || null;" +
				// Tìm mọi webpackChunk* trong window (không đoán tên cứng)
				"       if (!wreq) {" +
				"           var chunkKeys = Object.keys(window).filter(function(k){return k.startsWith('webpackChunk');});" +
				"           for (var ck=0; ck<chunkKeys.length && !wreq; ck++) {" +
				"               try { window[chunkKeys[ck]].push([[Math.random()],{},function(r){wreq=r;}]); } catch(e){}" +
				"           }" +
				"       }" +
				"       if (wreq && wreq.c) {" +
				"           var ckeys=Object.keys(wreq.c);" +
				"           for (var j=0;j<ckeys.length;j++) {" +
				"               var entry=wreq.c[ckeys[j]];" +
				"               var exp=entry&&entry.exports;" +
				"               if(exp&&(_deepFind(exp.default)||_deepFind(exp))){" +
				"                   console.log('[ZAuto] API found in webpack cache');" +
				"                   return true;" +
				"               }" +
				"           }" +
				"       }" +
				// Fallback: quét req.m nếu cache chưa load đủ
				"       if (wreq && wreq.m) {" +
				"           var mkeys=Object.keys(wreq.m);" +
				"           for (var mi=0;mi<mkeys.length;mi++){" +
				"               try{" +
				"                   var mm=wreq(mkeys[mi]); var me=mm&&(mm.default||mm);" +
				"                   if(me&&_isApi(me)){window.zMessenger=me;return true;}" +
				"               }catch(e){}" +
				"           }" +
				"       }" +
				"   } catch(e1) {}" +

				// ── TẦNG 2: REACT FIBER / REDUX STORE HIJACK ────────────────────────
				"   try {" +
				"       var roots=[document.querySelector('#app'),document.querySelector('#main-app')," +
				"                  document.querySelector('[class*=chat-window]'),document.querySelector('[class*=MessageList]')]" +
				"                 .filter(Boolean);" +
				"       for (var r=0;r<roots.length;r++) {" +
				"           var rk=Object.keys(roots[r]).find(function(k){return k.startsWith('__reactFiber')||k.startsWith('__reactContainer');});" +
				"           if (!rk) continue;" +
				"           var nd=roots[r][rk]; var dep=0;" +
				"           while(nd && dep<1000){" +
				"               var props=nd.memoizedProps||nd.pendingProps;" +
				"               if (props && props.store && typeof props.store.getState==='function') {" +
				"                   var st=props.store.getState();" +
				"                   if (_deepFind(st)) { console.log('[ZAuto] API found in Redux store'); return true; }" +
				"               }" +
				// Quét thêm memoizedState (Zustand/Context)
				"               var ms=nd.memoizedState;" +
				"               if (ms && ms.memoizedState && _deepFind(ms.memoizedState)) return true;" +
				"               nd=nd.child||nd.sibling||(nd.return?nd.return.sibling:null); dep++;" +
				"           }" +
				"       }" +
				"   } catch(e2) {}" +

				// ── TẦNG 3: HOOK XHR + FETCH — Bắt URL thật khi Zalo tự gửi tin ────
				// Dùng khi 2 tầng trên thất bại — lần sau Zalo gửi tin ta có URL
				"   if (!window._zauto_hook_set) {" +
				"       window._zauto_hook_set = true;" +
				"       try {" +
				"           var oXHR=window.XMLHttpRequest.prototype.open;" +
				"           window.XMLHttpRequest.prototype.open=function(method,url){" +
				"               if(typeof url==='string'&&(url.includes('sendmsg')||url.includes('send_msg')||url.includes('message/send')))" +
				"                   window._zauto_send_url=url;" +
				"               return oXHR.apply(this,arguments);" +
				"           };" +
				"           var oFetch=window.fetch;" +
				"           window.fetch=function(input,init){" +
				"               var url=typeof input==='string'?input:(input&&input.url||'');" +
				"               if(url.includes('sendmsg')||url.includes('send_msg')||url.includes('message/send')){" +
				"                   window._zauto_send_url=url;" +
				"                   if(init&&init.body){try{window._zauto_last_payload=JSON.parse(init.body);}catch(e){}}" +
				"               }" +
				"               return oFetch.apply(this,arguments);" +
				"           };" +
				"       } catch(e3) {}" +
				"   }" +

				"   return !!window.zMessenger;" +
				"}" +
				"_discoverApi();" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 1: MỞ ĐÚNG NHÓM (GIỮ NGUYÊN + TĂNG TIMEOUT 3500ms)
                // ─────────────────────────────────────────────────────────────
                "function _openGroup(cb) {" +
				"   if (!_convId || _convId==='') {" +
				// Không có convId — kiểm tra xem đang mở đúng nhóm chưa bằng _search (tên nhóm)
				"       if (_search && _search.length > 1) {" +
				"           var nameEls = document.querySelectorAll('.conv-item-title__name,[class*=conv-name],[class*=group-name]');" +
				"           for (var ni=0; ni<nameEls.length; ni++) {" +
				"               if ((nameEls[ni].textContent||'').trim().includes(_search.substring(0,15))) {" +
				"                   var convItem2 = nameEls[ni].closest('.msg-item,.conv-item');" +
				"                   if (convItem2) { convItem2.click(); setTimeout(function(){cb(true);},2000); return; }" +
				"               }" +
				"           }" +
				"       }" +
				"       cb(true); return;" +
				"   }" +
                "   var item = document.querySelector('.msg-item[anim-data-id='+_convId+'] .conv-item')" +
                "           || document.querySelector('.msg-item[anim-data-id='+_convId+']')" +
                "           || document.querySelector('[id*='+_convId+']');" +
                "   if (!item) {" +
                "       var all = document.querySelectorAll('.msg-item,.conv-item');" +
                "       for (var i=0;i<all.length;i++) {" +
                "           var rk=Object.keys(all[i]).find(k=>k.startsWith('__reactFiber')||k.startsWith('__reactProps'));" +
                "           if (rk && all[i][rk]) {" +
                "               var p=all[i][rk].memoizedProps||all[i][rk].pendingProps;" +
                "               if (p&&((p.session&&String(p.session.id)===_convId)||(p.convId&&String(p.convId)===_convId))) {item=all[i];break;}" +
                "           }" +
                "       }" +
                "   }" +
                "   if (!item) { cb(false); return; }" +
                "   item.scrollIntoView({block:'center'}); item.click();" +
                "   var rk=Object.keys(item).find(k=>k.startsWith('__reactEventHandlers')||k.startsWith('__reactFiber'));" +
                "   if (rk&&item[rk]) {" +
                "       var h=item[rk].onClick||(item[rk].return&&item[rk].return.memoizedProps&&item[rk].return.memoizedProps.onClick);" +
                "       if (h) h({preventDefault:function(){},stopPropagation:function(){}});" +
                "   }" +
                "   setTimeout(function(){cb(true);}, 3500);" +
                "}" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 2: TÌM NODE TIN NHẮN (GIỮ NGUYÊN TOÀN BỘ LOGIC CŨ)
                // ─────────────────────────────────────────────────────────────
                "function _findNode() {" +
				"   var node = null;" +
				"   var isVoice = _search.toLowerCase().includes('tin nh\\u1eafn tho\\u1ea1i')||_search.toLowerCase().includes('[tin nh\\u1eafn tho\\u1ea1i]')||_search.toLowerCase().includes('voice')||_search.toLowerCase().includes('audio');" +

				// ── ƯU TIÊN 0: data-qid parse — nguồn vàng chứa msgId thật ──────────
				// Format: "senderId@convId_msgId_groupId"
				"   var _parseQid = function(el) {" +
				"       var qv = el && el.getAttribute && el.getAttribute('data-qid');" +
				"       if (!qv) return null;" +
				"       var at = qv.indexOf('@'); var parts = qv.split('_');" +
				"       if (parts.length < 2) return null;" +
				"       var afterAt = at >= 0 ? qv.substring(at+1) : qv;" +
				"       var subParts = afterAt.split('_');" +
				"       return { msgId: subParts[1]||parts[1]||'', senderId: at>=0 ? qv.substring(0,at) : '', convId: subParts[0]||'', groupId: subParts[2]||'' };" +
				"   };" +

				// Tìm tất cả [data-qid] rồi match với _targetId hoặc _convId
				"   if (_targetId && _targetId.length > 4 && !_targetId.startsWith('TIME_') && !_targetId.startsWith('VIRTUAL_')) {" +
				"       var qframes = document.querySelectorAll('[data-qid]');" +
				"       for (var qi=0; qi<qframes.length; qi++) {" +
				"           var qp = _parseQid(qframes[qi]);" +
				"           if (qp && qp.msgId === _targetId) { node = qframes[qi]; break; }" +
				// Fallback: includes check
				"           if (!node && (qframes[qi].getAttribute('data-qid')||'').includes(_targetId)) { node = qframes[qi]; break; }" +
				"       }" +
				"   }" +

				// ── ƯU TIÊN 1: message-frame_[convId] — ID thực của Zalo Web ────────
				// Zalo Web dùng id="message-frame_[convId]" KHÔNG PHẢI bb_msg_id
				"   if (!node && _convId && _convId.length > 3) {" +
				"       node = document.querySelector('#message-frame_'+_convId)" +
				"           || document.querySelector('[id=\"message-frame_'+_convId+'\"]');" +
				// Nếu có nhiều tin trong nhóm, lấy tin CUỐI CÙNG của convId đó
				"       if (!node) {" +
				"           var mframes = document.querySelectorAll('[id^=\"message-frame_\"]');" +
				"           for (var mfi=mframes.length-1; mfi>=0; mfi--) {" +
				"               if (mframes[mfi].id === 'message-frame_'+_convId) { node=mframes[mfi]; break; }" +
				"           }" +
				"       }" +
				"   }" +

				// ── ƯU TIÊN 2: text-mCntr_[senderId]-[convId]-[msgId]-[groupId] ─────
				// Format id: "text-mCntr_senderId-convId-msgId-groupId"
				"   if (!node && _targetId && _targetId.length > 4) {" +
				"       var mCntrs = document.querySelectorAll('[id^=\"text-mCntr_\"]');" +
				"       for (var tci=0; tci<mCntrs.length; tci++) {" +
				"           if ((mCntrs[tci].id||'').includes(_targetId)) { node = mCntrs[tci].closest('[data-qid],[id^=\"message-frame_\"]') || mCntrs[tci]; break; }" +
				"       }" +
				"   }" +

				// ── ƯU TIÊN 3: Tin THOẠI — tìm theo class audio/voice ───────────────
				"   if (!node && isVoice) {" +
				"       var voiceBubbles = document.querySelectorAll('[class*=audio],[class*=voice-msg],[class*=VoiceMsg],[class*=AudioMessage],[class*=v-audio],.icon-voice,.ico-voice');" +
				"       if (voiceBubbles.length > 0) {" +
				"           node = voiceBubbles[voiceBubbles.length-1];" +
				"           var vc = node.closest('[data-qid],[id^=\"message-frame_\"],[id^=msg_],[id^=msg-],[data-msg-id],.chat-bubble,.message-bubble,[class*=chat-message]');" +
				"           if (vc) node = vc;" +
				"       }" +
				"       if (!node) {" +
				"           var allItems = document.querySelectorAll('[id^=\"message-frame_\"],[data-qid],[id^=msg_],[id^=msg-],.chat-bubble,.chat-item');" +
				"           for (var vi=allItems.length-1; vi>=0; vi--) {" +
				"               var vhtml=(allItems[vi].innerHTML||'').toLowerCase();" +
				"               if (vhtml.includes('ico-voice')||vhtml.includes('v-audio')||vhtml.includes('fa-playcircle')||vhtml.includes('audio-time')||vhtml.includes('audio-duration')) { node=allItems[vi]; break; }" +
				"           }" +
				"       }" +
				"   }" +

				// ── ƯU TIÊN 4: Tin TEXT — tìm theo nội dung _search ─────────────────
				"   if (!node && !isVoice && _search && _search.length > 2) {" +
				"       var allMsgs = document.querySelectorAll('[data-qid],[id^=\"message-frame_\"],[id^=msg_],[id^=msg-],.chat-bubble,.chat-item');" +
				"       for (var smi=allMsgs.length-1; smi>=0; smi--) {" +
				"           if ((allMsgs[smi].innerText||allMsgs[smi].textContent||'').includes(_search)) { node=allMsgs[smi]; break; }" +
				"       }" +
				"   }" +

				// ── FALLBACK: tin cuối cùng trong chat ──────────────────────────────
				"   if (!node) {" +
				"       var lasts = document.querySelectorAll('[data-qid],[id^=\"message-frame_\"],[id^=msg_],[id^=msg-],.chat-bubble,.chat-item');" +
				"       if (lasts.length > 0) node = lasts[lasts.length-1];" +
				"   }" +

				"   return node;" +
				"}" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 3: TRÍCH XUẤT REACT OBJECT + REAL ID TỪ FIBER
                // (GIỮ NGUYÊN TẦNG 0 + FIBER ĐI NGƯỢC 10 TẦNG + QUÉT CON)
                // ─────────────────────────────────────────────────────────────
                "function _extractObj(node) {" +
				"   var res = {id: _targetId, obj: null};" +
				"   if (!node) return res;" +

				// ── TẦNG 0A: Cache lookup ───────
				"   if (_targetId && _targetId.length>4 && !_targetId.startsWith('TIME_') && !_targetId.startsWith('VIRTUAL_')) {" +
				"       var cached = window._zauto_msg_cache && window._zauto_msg_cache[_targetId];" +
				"       if (cached) { res.id=cached.globalMsgId||cached.msgId||_targetId; res.obj=cached; return res; }" +
				"   }" +

				// ── TẦNG 0B: Parse data-qid trực tiếp ─────────────
				"   var qEl = (node && node.getAttribute && node.getAttribute('data-qid')) ? node :" +
				"             (node && node.closest('[data-qid]')) || (node && node.querySelector('[data-qid]'));" +
				"   var qidRaw = qEl && qEl.getAttribute && qEl.getAttribute('data-qid');" +
				"   if (qidRaw) {" +
				"       var atIdx = qidRaw.indexOf('@');" +
				"       var senderId = atIdx >= 0 ? qidRaw.substring(0, atIdx) : '';" +
				"       var afterAt  = atIdx >= 0 ? qidRaw.substring(atIdx+1) : qidRaw;" +
				"       var qParts   = afterAt.split('_');" +
				"       var qConvId  = qParts[0] || _convId;" +
				"       var qMsgId   = qParts[1] || '';" +
				"       var qGroupId = qParts[2] || '';" +
				"       if (qMsgId && qMsgId.length > 4) {" +
				"           res.id = qMsgId;" +
				"           var textEl = node && (" +
				"               node.querySelector('[data-component=\"text-container\"] .text') ||" +
				"               node.querySelector('[data-component=\"text-container\"] span') ||" +
				"               node.querySelector('.text-message__container span.text') ||" +
				"               node.querySelector('[class*=text-message] span') ||" +
				"               node.querySelector('span.text')" +
				"           );" +
				"           var msgText = textEl ? textEl.textContent.trim() : _search;" +
				"           res.obj = {" +
				"               globalMsgId : qMsgId," +
				"               msgId       : qMsgId," +
				"               cliMsgId    : qMsgId," +
				"               ownerId     : senderId," +
				"               senderId    : senderId," +
				"               uid         : senderId," +
				"               convId      : qConvId," +
				"               groupId     : qGroupId," +
				"               msg         : msgText," +
				"               content     : msgText," +
				"               text        : msgText," +
				"               type        : 1" +
				"           };" +
				"           if (window._zauto_msg_cache) window._zauto_msg_cache[qMsgId] = res.obj;" +
				"           return res;" +
				"       }" +
				"   }" +

				// Đi ngược 10 tầng fiber.return
				"   var rk=Object.keys(node).find(k=>k.startsWith('__reactFiber')||k.startsWith('__reactProps'));" +
                "   if (rk && node[rk]) {" +
                "       var fn=node[rk]; var step=0;" +
                "       while(fn && step<10) {" +
                "           var p=fn.memoizedProps||fn.pendingProps;" +
                "           if (p) {" +
                "               var o=p.msg||p.message||p.data||p.item||p.msgData||p.msgInfo||p.messageData||p.payload||p.params;" +
                "               if (o&&typeof o==='object'&&(o.msgId||o.globalMsgId||o.cliMsgId)) {" +
                "                   res.id=String(o.msgId||o.globalMsgId||o.cliMsgId); res.obj=o; return res;" +
                "               }" +
                "           }" +
                "           fn=fn.return; step++;" +
                "       }" +
                "   }" +
                // Quét xuống các con
                "   var ch=node.querySelectorAll('*');" +
                "   for (var i=0;i<ch.length;i++) {" +
                "       var ck=Object.keys(ch[i]).find(k=>k.startsWith('__reactFiber')||k.startsWith('__reactProps'));" +
                "       if (ck&&ch[i][ck]) {" +
                "           var cp=ch[i][ck].memoizedProps||ch[i][ck].pendingProps||{};" +
                "           var co=cp.msg||cp.message||cp.data||cp.item||cp.msgData||cp.msgInfo||cp.messageData||cp.payload||cp.params;" +
                "           if (co&&typeof co==='object') {" +
                "               var cid=String(co.msgId||co.globalMsgId||co.cliMsgId||'');" +
                "               if (cid&&cid.length>4){res.id=cid;res.obj=co;return res;}" +
                "           }" +
                "       }" +
                "   }" +
                // Tầng 0: React Conversation Store (giữ nguyên từ bản cũ)
                "   if (_targetId&&_targetId.length>3&&!_targetId.startsWith('TIME_')) {" +
                "       try {" +
                "           var roots=[document.getElementById('app'),document.querySelector('#main-app'),document.querySelector('[class*=chat-window]'),document.querySelector('[class*=conversation]')].filter(Boolean);" +
                "           outer: for (var ri=0;ri<roots.length;ri++) {" +
                "               var rrk=Object.keys(roots[ri]).find(k=>k.startsWith('__reactFiber'));" +
                "               if (!rrk) continue;" +
                "               var nd=roots[ri][rrk]; var depth=0;" +
                "               while(nd&&depth<80){" +
                "                   var ms=nd.memoizedState;" +
                "                   if (ms){var arr=ms.memoizedState||ms.queue; if(Array.isArray(arr)){for(var mi=0;mi<arr.length;mi++){var mm=arr[mi]; if(mm&&typeof mm==='object'){var fid=String(mm.msgId||mm.globalMsgId||mm.cliMsgId||''); if(fid===_targetId||fid===res.id){res.id=fid;res.obj=mm;break outer;}}}}}" +
                "                   nd=nd.child||nd.sibling||(nd.return?nd.return.sibling:null); depth++;" +
                "               }" +
                "           }" +
                "       } catch(e) {}" +
                "   }" +
                "   if (res.id&&res.id.length>4) res.id=res.id.replace('msg-','').replace('msg_','');" +
				// ── TẦNG EXTRA MỚI THÊM VÀO ĐÂY ──
				"   if (!res.obj || !res.id || res.id.length < 5) {" +
				"       var qnode = node.closest('[data-qid]') || node.querySelector('[data-qid]') || node;" +
				"       var qid = qnode ? qnode.getAttribute('data-qid') : null;" +
				"       if (qid) {" +
				"           var parts = qid.split('_');" +
				"           if (parts.length >= 2) {" +
				"               var rawMsgId = parts[1];" +
				"               var senderPart = parts[0].split('@');" +
				"               var senderId = senderPart[0]||'';" +
				"               var convIdFromQid = senderPart[1]||_convId;" +
				"               if (rawMsgId && rawMsgId.length > 4) {" +
				"                   res.id = rawMsgId;" +
				"                   if (!res.obj) res.obj = {" +
				"                       globalMsgId: rawMsgId," +
				"                       msgId: rawMsgId," +
				"                       ownerId: senderId," +
				"                       senderId: senderId," +
				"                       cliMsgId: rawMsgId," +
				"                       msg: node ? (node.innerText||node.textContent||'').trim().substring(0,200) : _search," +
				"                       type: 1" +
				"                   };" +
				"               }" +
				"           }" +
				"       }" +
				"   }" +
				// ── KẾT THÚC TẦNG EXTRA ──
				"   return res;" +
				"}" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 4: ĐIỀN TEXT + GỬI (GIỮ NGUYÊN SELECTOR ĐẦY ĐỦ)
                // ─────────────────────────────────────────────────────────────
                "function _typeAndSend() {" +
				// Ẩn bàn phím TRƯỚC MỌI THỨ: blur element đang focus, body.focus() chặn Android IME
				"   try { var _ae=document.activeElement; if(_ae&&_ae!==document.body){_ae.blur();} document.body.focus(); } catch(e) {}" +
				"   var input = document.querySelector('#chat-input-content')" +
				"            || document.querySelector('#richInput')" +
				"            || document.querySelector('[contenteditable=true][class*=chat-input]')" +
				"            || document.querySelector('[contenteditable=true][data-lexical-editor]')" +
				"            || document.querySelector('[contenteditable=true][role=textbox]')" +
				"            || document.querySelector('[contenteditable=true]')" +
				"            || document.querySelector('.chat-input');" +
				"   if (!input) { ZAutoBridge.onLoginSuccess('TRIGGER_VISION_FALLBACK',''); return; }" +
				"   input.setAttribute('readonly','true');" +
				"   input.focus();" +
				"   input.removeAttribute('readonly');" +
				// Xóa toàn bộ text cũ bằng selectAll trước
				"   try { document.execCommand('selectAll',false,null); document.execCommand('delete',false,null); } catch(ex) {}" +
				"   input.innerHTML = '';" +
				// Ghi text mới
				"   try { document.execCommand('insertText',false,_reply); } catch(ex) {}" +
				// Fallback nếu execCommand không hoạt động
				"   if (!input.textContent.trim() || input.textContent.trim() !== _reply) {" +
				"       input.innerHTML = '';" +
				"       input.textContent = _reply;" +
				// Trigger React bằng cách set value qua native setter
				"       var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLElement.prototype,'innerHTML') || Object.getOwnPropertyDescriptor(window.Element.prototype,'innerHTML');" +
				"       if (nativeInputValueSetter && nativeInputValueSetter.set) { nativeInputValueSetter.set.call(input, _reply); }" +
				"   }" +
                "   input.dispatchEvent(new Event('input',{bubbles:true}));" +
				"   input.dispatchEvent(new Event('change',{bubbles:true}));" +
				// Tầng 1: blur sau khi điền
				"   input.blur();" +
				"   document.body.focus();" +
				"   setTimeout(function() {" +
				// Tầng 2: blur trước khi click gửi
				"       try { var _ae2=document.activeElement; if(_ae2&&_ae2!==document.body){_ae2.blur();} } catch(e){}" +
				"       var iSend = document.querySelector('i.fa.fa-Sent-msg_24_Line')" +
				"                || document.querySelector('.fa-Sent-msg_24_Line')" +
				"                || document.querySelector('[class*=Sent-msg_24_Line]');" +
				"       var btnSend = iSend ? (iSend.closest('.z--btn--v2')||iSend.closest('button')||iSend.parentNode) : null;" +
				"       if (!btnSend) btnSend = document.querySelector('#chat-input-container-id .send-msg-btn')" +
				"                           || document.querySelector('[data-translate-title=STR_SEND]');" +
				"       if (btnSend) {" +
				"           btnSend.click();" +
				"           btnSend.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));" +
				"       }" +
				"       input.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,cancelable:true,keyCode:13,key:'Enter',which:13}));" +
				"       input.dispatchEvent(new KeyboardEvent('keypress',{bubbles:true,cancelable:true,keyCode:13,key:'Enter',which:13}));" +
				"       input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,cancelable:true,keyCode:13,key:'Enter',which:13}));" +
				// Tầng 3: readonly lock + blur + body.focus sau Enter
				"       input.setAttribute('readonly','true');" +
				"       input.blur();" +
				"       document.body.focus();" +
				"       setTimeout(function(){" +
				"           input.removeAttribute('readonly');" +
				"           var chk=document.querySelector('#chat-input-content,#richInput,[contenteditable=true]');" +
				"           var ok=!chk||chk.innerHTML===''||chk.innerHTML==='<br>'||chk.textContent.trim()==='';" +
				"           ZAutoBridge.onLoginSuccess(ok?'Chốt DOM UI QUOTE OK':'TRIGGER_VISION_FALLBACK','');" +
				"       },500);" +
				"   },400);" +
                "}" +

                // ─────────────────────────────────────────────────────────────
                // BƯỚC 5: KIỂM TRA QUOTE BANNER HIỆN RA
                // ─────────────────────────────────────────────────────────────
                "function _waitBanner(cb, maxMs) {" +
                "   var t0=Date.now();" +
                "   var iv=setInterval(function(){" +
                "       var b=document.querySelector('.chat-box-input__heading .quote-banner')" +
                "           ||document.querySelector('.rel.quote-banner')" +
                "           ||document.querySelector('[class*=quote-banner]')" +
                "           ||document.querySelector('[class*=reply-banner]')" +
                "           ||document.querySelector('[class*=ReplyBanner]')" +
                "           ||document.querySelector('[class*=quote-msg]')" +
                "           ||document.querySelector('[class*=QuoteMsg]');" +
                "       if (b||Date.now()-t0>maxMs){clearInterval(iv);cb(!!b);}" +
                "   },80);" +
                "}" +

                // ─────────────────────────────────────────────────────────────
				// BƯỚC 6B: LONG PRESS — phương án phòng bị mở popup Zalo
				// ─────────────────────────────────────────────────────────────
				"function _longPress(node, doneCb) {" +
				"   if (!node) { doneCb(false); return; }" +
				"   node.scrollIntoView({block:'center', behavior:'instant'});" +
				"   setTimeout(function() {" +
				// Tìm element con nhỏ nhất có nội dung thật — ưu tiên audio container, sau đó text bubble
				"       var bubble = node.querySelector('[class*=audio],[class*=voice-msg],[class*=VoiceMsg],[class*=v-audio],.ico-voice,.icon-voice')" +
				"                 || node.querySelector('.card--text,.card-content,[class*=bubble],[class*=chat-item__content],.message-chat-inner,[class*=msg-content],[class*=message-content]')" +
				"                 || node.querySelector('span[class],p[class],div[class*=text]')" +
				"                 || node;" +
				// Nếu bubble vẫn là node cha (không tìm được con) → đi xuống tìm con có kích thước nhỏ hơn
				"       if (bubble === node && node.children.length > 0) {" +
				"           var smallest = node; var smallestArea = node.offsetWidth * node.offsetHeight;" +
				"           var allChildren = node.querySelectorAll('*');" +
				"           for (var ci=0; ci<allChildren.length; ci++) {" +
				"               var ch = allChildren[ci];" +
				"               var area = ch.offsetWidth * ch.offsetHeight;" +
				"               if (area > 100 && area < smallestArea) { smallest = ch; smallestArea = area; }" +
				"           }" +
				"           if (smallest !== node) bubble = smallest;" +
				"       }" +
				"       var rect = bubble.getBoundingClientRect();" +
				"       var vw = window.innerWidth||document.documentElement.clientWidth;" +
				"       var vh = window.innerHeight||document.documentElement.clientHeight;" +
				"       if (rect.top < 0 || rect.bottom > vh || rect.height === 0) {" +
				"           node.scrollIntoView({block:'center', behavior:'smooth'});" +
				"           rect = bubble.getBoundingClientRect();" +
				"       }" +
				"       var cx = Math.max(10, Math.min(rect.left + rect.width/2, vw-10));" +
				"       var cy = Math.max(10, Math.min(rect.top  + rect.height/2, vh-10));" +
				"       var probes = [bubble, node];" +
				"       var triggered = false;" +
				"       for (var i=0;i<probes.length;i++) {" +
				"           var rk=Object.keys(probes[i]).find(k=>k.startsWith('__reactEventHandlers')||k.startsWith('__reactFiber'));" +
				"           if (rk&&probes[i][rk]) {" +
				"               var fib=probes[i][rk];" +
				"               var lp = (fib.memoizedProps&&(fib.memoizedProps.onLongPress||fib.memoizedProps.onContextMenu))" +
				"                     || (fib.return&&fib.return.memoizedProps&&(fib.return.memoizedProps.onLongPress||fib.return.memoizedProps.onContextMenu));" +
				"               if (typeof lp==='function') {" +
				"                   try { lp({preventDefault:function(){},stopPropagation:function(){},bubbles:true,clientX:cx,clientY:cy}); triggered=true; break; }" +
				"                   catch(ex) {}" +
				"               }" +
				"           }" +
				"       }" +
				"       try {" +
				"           bubble.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,button:2}));" +
				"       } catch(e) {}" +
				"       try {" +
				"           var mkT=function(id,el){try{return new Touch({identifier:id,target:el,clientX:cx,clientY:cy,radiusX:5,radiusY:5,rotationAngle:0,force:1});}catch(e){return null;}};" +
				"           var tLp=mkT(201,bubble);" +
				"           if(tLp) {" +
				"               bubble.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,cancelable:true,touches:[tLp],targetTouches:[tLp],changedTouches:[tLp]}));" +
				"               setTimeout(function(){" +
				"                   bubble.dispatchEvent(new TouchEvent('touchend',{bubbles:true,cancelable:true,touches:[],targetTouches:[],changedTouches:[tLp]}));" +
				"               }, 650);" +
				"           }" +
				"       } catch(te) {}" +

				"       // Đợi 750ms cho popup Zalo animate xong → tìm click 'Trả lời'" +
				"       setTimeout(function() {" +
				"           var replyBtn = null;" +
				"           // Tìm trong context-menu / popup đang hiện" +
				"           var menuItems = document.querySelectorAll('[class*=context-menu] [class*=item],[class*=popup] [class*=item],[class*=menu] li,[role=menuitem],li');" +
				"           for (var mi=0; mi<menuItems.length; mi++) {" +
				"               var mt = (menuItems[mi].textContent||'').trim();" +
				"               if (mt==='Trả lời'||mt==='Reply') { replyBtn=menuItems[mi]; break; }" +
				"           }" +
				"           // Fallback: quét toàn DOM — chỉ lấy element đang visible" +
				"           if (!replyBtn) {" +
				"               var allEls = document.querySelectorAll('span,div,li,button,a,p');" +
				"               for (var ei=0; ei<allEls.length; ei++) {" +
				"                   var et=(allEls[ei].textContent||'').trim();" +
				"                   if ((et==='Trả lời'||et==='Reply') && allEls[ei].offsetParent!==null) {" +
				"                       replyBtn=allEls[ei]; break;" +
				"                   }" +
				"               }" +
				"           }" +
				"           if (replyBtn) {" +
				"               replyBtn.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));" +
				"               replyBtn.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}));" +
				"               replyBtn.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true}));" +
				"               replyBtn.click();" +
				"               triggered=true;" +
				"           }" +
				"           doneCb(triggered);" +
				"       }, 750);" +

				"   }, 300);" +
				"}" +
				"function _doSend(node, realId, reactObj) {" +
				"   _discoverApi();" +
				"   var _sendFn = window.zMessenger && (" +
				"       window.zMessenger.sendMessage ||" +
				"       window.zMessenger.sendQuoteMsg ||" +
				"       window.zMessenger.replyMessage ||" +
				"       window.zMessenger.sendTextMessage ||" +
				"       window.zMessenger.sendMsg" +
				"   );" +
				"   if (typeof _sendFn === 'function') {" +
				"       try {" +
				"           var req = {toid:_convId, msg:_reply, type:1};" +
				"           var validId = realId && realId.length>4 && !realId.startsWith('TIME_') && !realId.startsWith('VIRTUAL_') && !realId.startsWith('CONTENT_') && !realId.startsWith('CACHE_');" +
				"           if (validId) {" +
				"               req.quote = reactObj ? {" +
				"                   globalMsgId: realId," +
				"                   ownerId: reactObj.ownerId||reactObj.senderId||reactObj.uid||''," +
				"                   dName:   reactObj.dName||reactObj.senderName||reactObj.fromName||''," +
				"                   msg:     reactObj.content||reactObj.msg||reactObj.text||_search," +
				"                   type:    reactObj.msgType||reactObj.type||1" +
				"               } : {globalMsgId:realId, msg:_search, type:1};" +
				"           }" +
				"           _sendFn.call(window.zMessenger, req);" +
				"           ZAutoBridge.onLoginSuccess('Chốt API QUOTE OK','');" +
				"           return;" +
				"       } catch(apiErr) { console.log('ZAuto API fail:', String(apiErr)); }" +
				"   }" +
				"   try {" +
				"       _superDblClick(node, function(reactHandled) {" +
				"           _waitBanner(function(bannerOk) {" +
				"               if (bannerOk) {" +
				"                   _typeAndSend();" +
				"               } else {" +
				"                   _longPress(node, function(lpTriggered) {" +
				"                       _waitBanner(function(bannerOk2) {" +
				"                           if (bannerOk2) {" +
				"                               _typeAndSend();" +
				"                           } else {" +
				"                               var rb=null, els=document.querySelectorAll('span,div,li,button,a');" +
				"                               for(var k=0;k<els.length;k++){" +
				"                                   var kt=(els[k].textContent||'').trim();" +
				"                                   if((kt==='Trả lời'||kt==='Reply')&&els[k].offsetParent!==null){rb=els[k];break;}" +
				"                               }" +
				"                               if(rb){ rb.click(); setTimeout(function(){_waitBanner(function(b3){_typeAndSend();},1000);},400); }" +
				"                               else { _typeAndSend(); }" +
				"                           }" +
				"                       }, 1800);" +
				"                   });" +
				"               }" +
				"           }, 1800);" +
				"       });" +
				"   } catch(domErr) {" +
				"       ZAutoBridge.onLoginSuccess('TRIGGER_VISION_FALLBACK','');" +
				"   }" +
				"}" +
				"function _superDblClick(node, doneCb) {" +
                "   if (!node) { doneCb(false); return; }" +
                // Scroll đến tin, đợi render xong rồi mới đo tọa độ
                "   node.scrollIntoView({block:'center', behavior:'instant'});" +
                "   setTimeout(function() {" +

                // Tìm bong bóng chính xác nhất
                // Tìm element con nhỏ nhất có nội dung thật — ưu tiên audio container, sau đó text bubble
				"       var bubble = node.querySelector('[class*=audio],[class*=voice-msg],[class*=VoiceMsg],[class*=v-audio],.ico-voice,.icon-voice')" +
				"                 || node.querySelector('.card--text,.card-content,[class*=bubble],[class*=chat-item__content],.message-chat-inner,[class*=msg-content],[class*=message-content]')" +
				"                 || node.querySelector('span[class],p[class],div[class*=text]')" +
				"                 || node;" +
				// Nếu bubble vẫn là node cha (không tìm được con) → đi xuống tìm con có kích thước nhỏ hơn
				"       if (bubble === node && node.children.length > 0) {" +
				"           var smallest = node; var smallestArea = node.offsetWidth * node.offsetHeight;" +
				"           var allChildren = node.querySelectorAll('*');" +
				"           for (var ci=0; ci<allChildren.length; ci++) {" +
				"               var ch = allChildren[ci];" +
				"               var area = ch.offsetWidth * ch.offsetHeight;" +
				"               if (area > 100 && area < smallestArea) { smallest = ch; smallestArea = area; }" +
				"           }" +
				"           if (smallest !== node) bubble = smallest;" +
				"       }" +
                "       var rect = bubble.getBoundingClientRect();" +
                "       var vw = window.innerWidth||document.documentElement.clientWidth;" +
                "       var vh = window.innerHeight||document.documentElement.clientHeight;" +

                // Nếu bubble chưa vào viewport — scroll thêm lần nữa
                "       if (rect.top < 0 || rect.bottom > vh || rect.height === 0) {" +
                "           node.scrollIntoView({block:'center', behavior:'smooth'});" +
                "           rect = bubble.getBoundingClientRect();" +
                "       }" +

				// Double-click đúng chuẩn Zalo: click vào VÙNG TRỐNG trong hàng tin nhắn (bên ngoài bubble text)
				// Theo cấu trúc HTML: .message-frame là row toàn bộ, bubble là .text-message__container bên trong
				"       var row = node.closest('.message-frame,.message-container,[class*=message-row],[class*=chat-item],[class*=MessageItem]') || node;" +
				"       var rowRect = row.getBoundingClientRect();" +
				"       var bubbleRect = bubble.getBoundingClientRect();" +
				"       var cy = Math.max(10, Math.min(rowRect.top + rowRect.height/2, vh-10));" +
				"       var cx;" +
				// Kiểm tra vùng trống BÊN PHẢI bubble trong row
				"       if (rowRect.right - bubbleRect.right > 30) {" +
				"           cx = Math.min(bubbleRect.right + Math.floor((rowRect.right - bubbleRect.right)/2), vw-10);" +
				// Kiểm tra vùng trống BÊN TRÁI bubble trong row
				"       } else if (bubbleRect.left - rowRect.left > 30) {" +
				"           cx = Math.max(10, rowRect.left + Math.floor((bubbleRect.left - rowRect.left)/2));" +
				// Fallback: bubble chiếm gần hết row → click tâm bubble
				"       } else {" +
				"           cx = Math.max(10, Math.min(bubbleRect.left + bubbleRect.width/2, vw-10));" +
				"       }" +

                "       var wrapper = node.closest('.chat-message,.message-container,[class*=message-row],[class*=chat-item],[class*=MessageItem]') || node;" +
                "       var triggered = false;" +

                // ── CHIẾN LƯỢC A: Chọc thẳng React onDoubleClick handler ──────
                // Không cần tọa độ — mạnh nhất, không phụ thuộc layout
                "       var probes = [bubble, node, wrapper];" +
                "       try { var extra=node.querySelectorAll('[class*=chat-message],[class*=message-row],[class*=MessageItem]'); for(var pi=0;pi<Math.min(extra.length,5);pi++) probes.push(extra[pi]); } catch(ex) {}" +
                "       for (var i=0;i<probes.length;i++) {" +
                "           if (!probes[i]) continue;" +
                "           var rk=Object.keys(probes[i]).find(k=>k.startsWith('__reactEventHandlers')||k.startsWith('__reactFiber'));" +
                "           if (rk&&probes[i][rk]) {" +
                "               var fib=probes[i][rk];" +
                // Tìm handler onDoubleClick qua nhiều đường fiber
                "               var dbl = fib.onDoubleClick" +
                "                       ||(fib.memoizedProps&&fib.memoizedProps.onDoubleClick)" +
                "                       ||(fib.pendingProps&&fib.pendingProps.onDoubleClick)" +
                "                       ||(fib.return&&fib.return.memoizedProps&&fib.return.memoizedProps.onDoubleClick)" +
                "                       ||(fib.return&&fib.return.return&&fib.return.return.memoizedProps&&fib.return.return.memoizedProps.onDoubleClick);" +
                "               if (typeof dbl==='function') {" +
                "                   try {" +
                "                       dbl({preventDefault:function(){},stopPropagation:function(){},bubbles:true,clientX:cx,clientY:cy,nativeEvent:{clientX:cx,clientY:cy}});" +
                "                       triggered=true; break;" +
                "                   } catch(ex2) {}" +
                "               }" +
                "           }" +
                "       }" +

                // ── CHIẾN LƯỢC B: Chuỗi Mouse Events đầy đủ vào TÂM bubble ──
                // mousedown×2 → mouseup×2 → click(detail:1) → click(detail:2) → dblclick
                // Mô phỏng chính xác hành vi người dùng thật trên Chromium
                "       var fireMouseSeq = function(el) {" +
                "           el.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy}));" +
                "           el.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy}));" +
                "           el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:1,detail:1}));" +
                "           el.dispatchEvent(new MouseEvent('mouseup',  {bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:0,detail:1}));" +
                "           el.dispatchEvent(new MouseEvent('click',    {bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:0,detail:1}));" +
                "           setTimeout(function(){" +
                "               el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:1,detail:2}));" +
                "               el.dispatchEvent(new MouseEvent('mouseup',  {bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:0,detail:2}));" +
                "               el.dispatchEvent(new MouseEvent('click',    {bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:0,detail:2}));" +
                "               el.dispatchEvent(new MouseEvent('dblclick', {bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,buttons:0,detail:2}));" +
                "           }, 60);" +
                "       };" +
                // Bắn vào row tại tọa độ vùng trống đã tính (cx,cy) — đây là cách Zalo Web nhận double-click reply
				"       fireMouseSeq(row);" +
				"       setTimeout(function(){ fireMouseSeq(bubble); }, 30);" +

                // ── CHIẾN LƯỢC C: Touch Events đôi (Android WebView native) ──
                // Android đôi khi ưu tiên touch events hơn mouse events
                "       try {" +
                "           var mkTouch=function(id,el){try{return new Touch({identifier:id,target:el,clientX:cx,clientY:cy,radiusX:5,radiusY:5,rotationAngle:0,force:1});}catch(e){return null;}};" +
                "           var t1=mkTouch(101,bubble);" +
                "           if (t1) {" +
                "               bubble.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,cancelable:true,touches:[t1],targetTouches:[t1],changedTouches:[t1]}));" +
                "               bubble.dispatchEvent(new TouchEvent('touchend',  {bubbles:true,cancelable:true,touches:[],targetTouches:[],changedTouches:[t1]}));" +
                "               setTimeout(function(){" +
                "                   var t2=mkTouch(102,bubble);" +
                "                   if (!t2) return;" +
                "                   bubble.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,cancelable:true,touches:[t2],targetTouches:[t2],changedTouches:[t2]}));" +
                "                   bubble.dispatchEvent(new TouchEvent('touchend',  {bubbles:true,cancelable:true,touches:[],targetTouches:[],changedTouches:[t2]}));" +
                "               }, 80);" +
                "           }" +
                "       } catch(tex) {}" +

                // ── CHIẾN LƯỢC D: Pointer Events chuẩn W3C (Chrome 86+) ──────
                "       try {" +
                "           bubble.dispatchEvent(new PointerEvent('pointerover', {bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse'}));" +
                "           bubble.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse',pressure:0.5}));" +
                "           bubble.dispatchEvent(new PointerEvent('pointerup',   {bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse'}));" +
                "           setTimeout(function(){" +
                "               bubble.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse',pressure:0.5}));" +
                "               bubble.dispatchEvent(new PointerEvent('pointerup',  {bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse'}));" +
                "               bubble.dispatchEvent(new PointerEvent('click',      {bubbles:true,clientX:cx,clientY:cy,pointerId:1,isPrimary:true,pointerType:'mouse',detail:2}));" +
                "           }, 80);" +
                "       } catch(pex) {}" +

                // Sau tất cả chiến lược — gọi callback
                "       doneCb(triggered);" +
                "   }, 300);" +   // đợi scroll render
                "}" +
				// ─────────────────────────────────────────────────────────────
                // LUỒNG CHẠY CHÍNH (ĐÃ CẬP NHẬT GỌN GÀNG)
                // ─────────────────────────────────────────────────────────────
                "_openGroup(function(opened) {" +
                "   var node    = _findNode();" +
                "   var ext     = _extractObj(node);" +
                "   if (!opened) {" +
                "       console.log('ZAuto: group not opened, retry click convId='+_convId);" +
                "       var directItem = document.querySelector('[anim-data-id=\"'+_convId+'\"]');" +
                "       if (directItem) { directItem.click(); }" +
                "       setTimeout(function() {" +
                "           var n2=_findNode(); var e2=_extractObj(n2);" +
                "           if (!n2) { ZAutoBridge.onLoginSuccess('TRIGGER_VISION_FALLBACK',''); return; }" +
                "           _doSend(n2, e2.id, e2.obj);" +
                "       }, 2000);" +
                "       return;" +
                "   }" +
                "   _doSend(node, ext.id, ext.obj);" +
                "});" +

                "} catch(e) { console.log('ZAuto fatal:',String(e)); ZAutoBridge.onLoginSuccess('TRIGGER_VISION_FALLBACK',''); }" +
                "})();";

                // Tạm thời đưa WebView vào viewport để JS click/touch hoạt động
                // (chỉ cần 1x1px visible là đủ — không cần full screen)
                try {
                    ViewGroup.LayoutParams lp = webLayout.getLayoutParams();
                    if (lp instanceof FrameLayout.LayoutParams) {
                        FrameLayout.LayoutParams flp = (FrameLayout.LayoutParams) lp;
                        int oldLeft = flp.leftMargin;
                        int oldTop  = flp.topMargin;
                        flp.leftMargin = 0;
                        flp.topMargin  = 0;
                        webLayout.setLayoutParams(flp);
                        webLayout.requestLayout();
                        hiddenWebView.bringToFront();
                        hiddenWebView.requestFocus();

                        // Chạy JS sau 150ms (đủ để Android layout xong)
                        hiddenWebView.postDelayed(() -> {
                            hiddenWebView.evaluateJavascript(jsCode, null);
                            // Ẩn lại sau 8 giây (đủ cho toàn bộ flow click+send xong)
                            hiddenWebView.postDelayed(() -> {
                                try {
                                    flp.leftMargin = oldLeft;
                                    flp.topMargin  = oldTop;
                                    webLayout.setLayoutParams(flp);
                                    webLayout.requestLayout();
                                } catch (Exception ignored) {}
                            }, 8000);
                        }, 150);
                    } else {
                        hiddenWebView.evaluateJavascript(jsCode, null);
                    }
                } catch (Exception layoutEx) {
                    hiddenWebView.evaluateJavascript(jsCode, null);
                }
            } catch (Exception e) {
                Log.e(TAG, "Reply Engine Error", e);
            }
        }));

        safeActivity.runOnUiThread(ZaloWebManager::processReplyQueue);
    }

    // =========================================================
    // JAVA BRIDGE → NÉM VÀO RAM PYTHON THAY VÌ BROADCAST
    // =========================================================
    public static String currentImei = ""; // Thêm dòng này ngay trên WebAppInterface

    public static class WebAppInterface {
        Context mContext;
        WebAppInterface(Context c) { mContext = c; }

        @JavascriptInterface
        public void onHeartbeat(String ts, String imei) { // Thêm tham số imei
            lastHeartbeat = System.currentTimeMillis();
            if (imei != null && !imei.isEmpty() && !imei.equals("null")) {
                currentImei = imei; // Lưu IMEI lại khi JS gửi lên
            }
        }
        // ... (giữ nguyên các hàm bên dưới)

        @JavascriptInterface
        public void onLoginSuccess(String name, String avatar) {
            pythonMsgQueue.add("LOGIN_SUCCESS|||" + name + "|||" + avatar);
        }

        @JavascriptInterface
        public void onNewWebMsg(String group, String msg, String msgId, String conversationId) {
            pythonMsgQueue.add("WEB_NEW_MSG|||" + group + "|||" + msg + "|||" + msgId + "|||" + conversationId);
        }

        @JavascriptInterface
        public void onGroupListReceived(String jsonGroups) {
            pythonMsgQueue.add("GROUPS_DATA|||" + jsonGroups);
        }
		@JavascriptInterface
        public void onLogout() {
            pythonMsgQueue.add("ZALO_LOGOUT|||");
        }

        @JavascriptInterface
        public void onError(String code, String detail) {
            Log.e(TAG, "JS_ERROR: " + code + " - " + detail);
        }
    }

    // =========================================================
    // KHỞI TẠO WEBVIEW TƯƠNG THÍCH MỌI PHIÊN BẢN ANDROID 10 -> 15
    // =========================================================
    public static void initWebView(final Activity activity) {
        if (activity == null) return;
        activityRef = new WeakReference<>(activity);

        activity.runOnUiThread(() -> {
            try {
                if (hiddenWebView != null) return;

                webLayout = new FrameLayout(activity);
                hiddenWebView = new WebView(activity);

                // =========================================================
                // CẤU HÌNH LAYER TYPE - ÉP DÙNG HARDWARE ĐỂ VẼ QR CANVAS
                // =========================================================
                hiddenWebView.setLayerType(View.LAYER_TYPE_NONE, null);

                // Android 8+ trở lên: Ưu tiên tài nguyên hệ thống cho render process
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                    hiddenWebView.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, true);
                }

                // =========================================================
                // CẤU HÌNH WEBSETTINGS TƯƠNG THÍCH MỌI PHIÊN BẢN CHROME CORE
                // =========================================================
                WebSettings settings = hiddenWebView.getSettings();
                settings.setJavaScriptEnabled(true);
                settings.setDomStorageEnabled(true);
                settings.setDatabaseEnabled(true);
                settings.setAllowFileAccess(true);
                settings.setLoadsImagesAutomatically(true);
                settings.setMediaPlaybackRequiresUserGesture(false);
                settings.setCacheMode(WebSettings.LOAD_DEFAULT);
                settings.setNeedInitialFocus(false);
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
                settings.setUseWideViewPort(true);
                settings.setLoadWithOverviewMode(true);
                
                // BẬT ZOOM NGẦM ĐỂ TRÁNH CSS ẨN KHUNG QR ĐĂNG NHẬP
                settings.setSupportZoom(true);
                settings.setBuiltInZoomControls(true);
                settings.setDisplayZoomControls(false);

                // OffscreenPreRaster: Chỉ kích hoạt trên Android 11+ nhằm tối ưu tải trang ngầm
                settings.setOffscreenPreRaster(true);

                // ForceDark: Tắt chế độ tối trên Android 10+ để mã QR hiển thị rõ nét nhất
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                    settings.setForceDark(WebSettings.FORCE_DARK_OFF);
                }

                // =========================================================
                // ⚠️ BẮT BUỘC GIỮ USER AGENT DESKTOP
                // Để Zalo luôn kích hoạt phiên bản máy tính phục vụ cào quét tin ngầm
                // =========================================================
                settings.setUserAgentString(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                    "AppleWebKit/537.36 (KHTML, like Gecko) " +
                    "Chrome/136.0.0.0 Safari/537.36"
                );

                // =========================================================
                // QUẢN LÝ COOKIE THÀNH PHẦN THỨ BA
                // =========================================================
                CookieManager cookieManager = CookieManager.getInstance();
                cookieManager.setAcceptCookie(true);
                cookieManager.setAcceptThirdPartyCookies(hiddenWebView, true);

                hiddenWebView.addJavascriptInterface(new WebAppInterface(activity), "ZAutoBridge");
                hiddenWebView.setWebChromeClient(new WebChromeClient());

                // =========================================================
                // WEBVIEW CLIENT: XỬ LÝ LỖI MẠNG VÀ INJECT JS TỰ ĐỘNG
                // =========================================================
                hiddenWebView.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                        if (request != null && request.isForMainFrame()) {
                            Log.e(TAG, "Lỗi kết nối Zalo: " + error.getDescription());
                            view.postDelayed(() -> {
                                if (view != null) safeReload();
                            }, 5000);
                        }
                    }

                    @Override
                    public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                        // VÁ LỖI ANDROID 10: Bỏ qua lỗi bắt tay SSL do chứng chỉ trung gian Let's Encrypt hết hạn trên máy cũ
                        handler.proceed();
                    }

                    @Override
                    public void onPageFinished(WebView view, String url) {
                        super.onPageFinished(view, url);
                        CookieManager.getInstance().flush();
                        
                        // ĐÃ TẮT: Không tiêm JS cào tin nhắn của Java nữa vì Node.js đã lo việc này
                        /*
                        view.postDelayed(() -> {
                            try {
                                if (hiddenWebView != null) injectSidebarObserver(hiddenWebView);
                            } catch (Exception e) {
                                Log.e(TAG, "Inject Error", e);
                            }
                        }, 5000);
                        */
                    }
                    
                    @Override
                    public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                        Log.e(TAG, "WEBVIEW RENDER DEAD. RECOVERING...");
                        if (webLayout != null) webLayout.removeAllViews();
                        if (hiddenWebView != null) {
                            hiddenWebView.destroy();
                            hiddenWebView = null;
                        }
                        Activity act = activityRef != null ? activityRef.get() : null;
                        if (act != null) {
                            // Chờ 2 giây giải phóng luồng cũ rồi tự động khởi tạo lại hệ thống ngầm
                            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                                initWebView(act);
                            }, 2000);
                        }
                        return true;
                    }
                });

                hiddenWebView.loadUrl("https://id.zalo.me/account?continue=https://chat.zalo.me");

                FrameLayout.LayoutParams webParams = new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT
                );
                webLayout.addView(hiddenWebView, webParams);
                // Đẩy webLayout ra tọa độ âm (ngoài màn hình) ngay từ đầu để không che Kivy
				FrameLayout.LayoutParams rootParams = new FrameLayout.LayoutParams(1080, 2400);
				rootParams.leftMargin = -2000; 
				rootParams.topMargin = -2000;

				webLayout.setAlpha(0.01f);  
				webLayout.setTranslationZ(-100f); 

				if (webLayout.getParent() != null) {  
					((ViewGroup) webLayout.getParent()).removeView(webLayout);
				}

				activity.addContentView(webLayout, rootParams);

                hiddenWebView.setVisibility(View.VISIBLE);
                hiddenWebView.bringToFront();
                hiddenWebView.requestFocus();

                // KHỞI TẠO GIỌNG NÓI TIẾNG VIỆT CÓ BẢO VỆ FALLBACK
                if (tts == null) {
                    tts = new TextToSpeech(activity.getApplicationContext(), status -> {
                        if (status == TextToSpeech.SUCCESS) {
                            int result = tts.setLanguage(new Locale("vi", "VN"));
                            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                                // Nếu máy thiếu dữ liệu gói tiếng Việt, tự động lùi về ngôn ngữ mặc định của máy để tránh câm loa
                                tts.setLanguage(Locale.getDefault());
                                Log.w(TAG, "TTS: Thừa dữ liệu tiếng Việt, lùi về ngôn ngữ hệ thống thiết bị.");
                            }
                        }
                    });
                }

                // ĐÃ TẮT WATCHDOG: Giúp WebView ngủ đông hoàn toàn khi ẩn, không gây nóng máy
                // startWatchdog();

            } catch (Exception e) {
                Log.e(TAG, "Init Error", e);
            }
        });
    }

    // =========================================================
    // JS OBSERVER & API INTERNAL (CHẠY NGẦM 100%)
    // =========================================================
    public static void injectSidebarObserver(WebView view) {
        String js =
            "(function() {" +
            "   if(window.zauto_started) return;" +
            "   window.zauto_started = true;" +
            "   window.zauto_boot_time = Date.now();" +
            "   window.zauto_seen = {};" +
            "   window.zauto_seen_keys = [];" +

            // HÀM GỬI REPLY ĐA TẦNG (DÙNG SELECTOR CHUẨN + ENTER + BÁO CÁO TOAST)
            "   window.zautoSendReply = function(convId, fakeMsgId, text, groupName) {" +
            "       try {" +
            "           let item = document.querySelector('.msg-item[anim-data-id=' + convId + '] .conv-item');" +
            "           if(item) {" +
            "               let key = Object.keys(item).find(k => k.startsWith('__reactEventHandlers') || k.startsWith('__reactFiber'));" +
            "               if (key && item[key]) {" +
            "                   if (item[key].onClick) item[key].onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
            "                   else if (item[key].return && item[key].return.memoizedProps.onClick) item[key].return.memoizedProps.onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
            "               } else { item.click(); }" +
            "           }" +
            
            "           setTimeout(() => {" +
            "               let realMsgId = '';" +
            "               try {" +
            "                   let msgs = document.querySelectorAll('[id^=msg_]');" +
            "                   if (msgs && msgs.length > 0) {" +
            "                       let lastMsg = msgs[msgs.length - 1];" +
            "                       realMsgId = lastMsg.getAttribute('id').substring(4);" +
            "                   }" +
            "               } catch(err) { realMsgId = ''; }" +
            
            "               if (window.zMessenger && typeof window.zMessenger.sendMessage === 'function') {" +
            "                   let req = { toid: convId, msg: text, type: 1 };" +
            "                   if (realMsgId && realMsgId !== '') req.quote = { globalMsgId: realMsgId, msg: text, type: 1 };" +
            "                   window.zMessenger.sendMessage(req);" +
            "                   ZAutoBridge.onLoginSuccess('Đã chốt xong:', groupName);" + 
            "               } else {" +
            "                   let input = document.getElementById('richInput');" +
			"                   if(input) {" +
			"                       input.setAttribute('readonly','true'); input.focus(); input.removeAttribute('readonly');" +
			"                       input.innerHTML = '';" +
			"                       document.execCommand('insertText', false, text);" +
			"                       input.dispatchEvent(new Event('input', {bubbles:true}));" +
			"                       input.blur();" +
            "                       let attempts = 0;" +
            
            "                       let trySend = setInterval(() => {" +
            "                           attempts++;" +
            "                           let btnSend = null;" +
            "                           let primarySelector = '#chat-input-container-id > div.chat-input-container__right-layout > div.normal-buttons-group > div.send-msg-btn';" +
            "                           let fallbackSelectors = ['.fa-Sent-msg_24_Line', '[data-translate-title=STR_SEND]'];" +
            
            "                           let el = document.querySelector(primarySelector);" +
            "                           if (el) {" +
            "                               btnSend = el;" +
            "                           } else {" +
            "                               for (let sel of fallbackSelectors) {" +
            "                                   let fallbackEl = document.querySelector(sel);" +
            "                                   if (fallbackEl) {" +
            "                                       btnSend = fallbackEl.closest('.z--btn--v2') || fallbackEl.parentElement || fallbackEl;" +
            "                                       break;" +
            "                                   }" +
            "                               }" +
            "                           }" +
            
            "                           if (btnSend) {" +
            "                               btnSend.click();" +
            "                               let key = Object.keys(btnSend).find(k => k.startsWith('__reactEventHandlers') || k.startsWith('__reactFiber'));" +
            "                               if(key && btnSend[key] && btnSend[key].onClick) btnSend[key].onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
            "                           }" +
            
            "                           let enterEvent = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, keyCode: 13, which: 13, key: 'Enter', code: 'Enter' });" +
            "                           input.dispatchEvent(enterEvent);" +
            
            "                           if (input.innerHTML === '' || input.innerHTML === '<br>') {" +
            "                               clearInterval(trySend);" +
            "                               ZAutoBridge.onLoginSuccess('Đã chốt xong:', groupName);" + 
            "                           } else if (attempts > 12) {" +
            "                               clearInterval(trySend);" +
            "                           }" +
            "                       }, 250);" + 
            "                   }" +
            "               }" +
            "           }, 800);" + 
            "       } catch(e) {}" +
            "   };" +

            // HÀM QUÉT SIDEBAR (ĐÃ FIX ZALO ĐỔI GIAO DIỆN & TÌM ĐÚNG ID TIN)
            "   function scanConvItem(msgItemEl) {" +
            "       try {" +
            "           let convItem = msgItemEl.querySelector('.conv-item') || msgItemEl;" + 
            "           if(!convItem) return;" +
            
            "           let nameEl = convItem.querySelector('.conv-item-title__name, [class*=name]');" +
            "           let bodyEl = convItem.querySelector('.conv-item-body, [class*=snippet], [class*=message-text]');" +
            "           if(!nameEl) return;" + 
            "           let groupName = (nameEl.textContent || nameEl.innerText || '').trim();" +
            "           let msgText = bodyEl ? (bodyEl.textContent || bodyEl.innerText || '').trim() : '';" +
            
            "           let realMsgId = ''; var fullTxt = ''; let convId = '';" +
            
            // DEEP BYPASS: QUÉT VÉT CẠN MỌI TẦNG REACT FIBER (8 TẦNG) ĐỂ LỘT TRẦN ID BỊ GIẤU
            "           try {" +
			"               convId = msgItemEl.getAttribute('anim-data-id') || msgItemEl.id || '';" +
			"               let id1 = msgItemEl.getAttribute('data-msg-id') || (msgItemEl.dataset ? msgItemEl.dataset.msgId : '');" +
			"               if (id1 && id1.length > 5) realMsgId = id1;" +
			"               if (!realMsgId) {" +
			"                   let qidEl = msgItemEl.querySelector('[data-qid]') || msgItemEl.closest('[data-qid]');" +
			"                   let qid = qidEl ? qidEl.getAttribute('data-qid') : null;" +
			"                   if (qid) {" +
			"                       let qparts = qid.split('_');" +
			"                       if (qparts.length >= 2 && qparts[1] && qparts[1].length > 4) {" +
			"                           realMsgId = qparts[1];" +
			"                           if (!convId) { let sp = qparts[0].split('@'); if(sp[1]) convId = sp[1]; }" +
			"                       }" +
			"                   }" +
			"               }" +
            
            "               let keys = Object.keys(msgItemEl);" +
            "               let rK = keys.find(k => k.startsWith('__reactFiber') || k.startsWith('__reactProps'));" +
            "               if (rK && msgItemEl[rK]) {" +
			"                   let node = msgItemEl[rK];" +
			"                   if (node) {" +
			"                       let p = node.memoizedProps || node.pendingProps;" +
			"                       if(!convId && p && p.session) { convId = String(p.session.id); }" +
			"                       if(!convId && p && p.convId) { convId = String(p.convId); }" +
			"                   }" +
			"                   for(let step = 0; step < 8; step++) {" + 
            "                       if(!node) break;" +
            "                       let currProps = node.memoizedProps || node.pendingProps;" +
            "                       if (currProps) {" +
            "                           let o = currProps.msg || currProps.message || currProps.data || currProps.item || currProps;" +
            "                           if (o && typeof o === 'object') {" +
			"                               let foundId = o.msgId || o.messageId || o.cliMsgId || o.globalMsgId;" +
			"                               if (!foundId && o.timestamp) foundId = 'TS_' + o.timestamp;" + 
			"                               if (!realMsgId && foundId && String(foundId).length > 5) { realMsgId = String(foundId); }" +
			"                               if (!fullTxt && typeof o.content === 'string' && o.content.trim() !== '') { fullTxt = o.content; }" +
			"                               if (!convId && o.fromId) { convId = String(o.fromId); }" +
			"                               if (!convId && o.toId) { convId = String(o.toId); }" +
			"                           }" +
			"                           if (!convId && currProps.session && currProps.session.id) { convId = String(currProps.session.id); }" +
			"                           if (!convId && currProps.convId) { convId = String(currProps.convId); }" +
			"                           if (!convId && currProps.conversationId) { convId = String(currProps.conversationId); }" +
			"                       }" +
			"                       node = node.return;" +
            "                   }" +
            "               }" +
            "           } catch(err) {}" +
            
            "           if (fullTxt && fullTxt.length > msgText.length && !fullTxt.startsWith('{')) {" +
            "               msgText = fullTxt.trim();" +
            "           }" +
            
            "           let isVoiceNode = bodyEl ? bodyEl.querySelector('[class*=audio],[class*=voice],[class*=Voice],[class*=record],[class*=AudioMessage],[class*=VoiceMsg]') : null;" +
			"           if (!isVoiceNode && bodyEl) { let svgs = bodyEl.querySelectorAll('svg'); for (let s of svgs) { if (s.closest('[class*=audio],[class*=voice],[class*=record],[class*=Voice]')) { isVoiceNode = s; break; } } }" +
			"           let isTimeOnly = (isVoiceNode && bodyEl) ? (/^[0-9]{1,2}:[0-9]{2}$/.test(msgText) || /^[0-9]{1,2}:[0-9]{2}$/.test(bodyEl.innerText.trim())) : false;" +
            "           let seconds = -1; let isVoice = false;" +
            
            "           if (isVoiceNode || isTimeOnly) {" +
            "               isVoice = true;" +
            "               let rawBody = bodyEl.textContent || bodyEl.innerText || '';" +
            "               if (rawBody.indexOf(': ') > -1) {" +
            "                   msgText = rawBody.split(': ')[0] + ': [Tin nhắn thoại]';" +
            "               } else {" +
            "                   msgText = '[Tin nhắn thoại]';" +
            "               }" +
            "               try {" +
            "                   let timeNode = msgItemEl.querySelector('[class*=audio-time], [class*=duration], span[class*=time]');" +
            "                   if (timeNode) {" +
            "                       let durationText = timeNode.innerText.trim();" + 
            "                       if (durationText.includes(':')) {" +
            "                           let parts = durationText.split(':');" +
            "                           seconds = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);" +
            "                       }" +
            "                   }" +
            "               } catch(err) { seconds = -1; }" +
            "               msgText = msgText + '%%%' + seconds;" + 
            "           }" +

            "           if(!groupName) return;" +
            "           if(!msgText || msgText.length < 1) {" +
            "               setTimeout(() => { try { scanConvItem(msgItemEl); }catch(e){} }, 1000);" +
            "               return;" +
            "           }" +

            "           let timeEl = convItem.querySelector('.conv-item-title__time, [class*=time]');" +
			"           let timeString = timeEl ? (timeEl.textContent || '').trim() : '';" +
			"           let senderEl = msgItemEl ? (msgItemEl.querySelector('.sender-name,[class*=sender],[class*=author],[class*=from-name]') || msgItemEl.querySelector('[class*=conv-item-title__name]')) : null;" +
			"           let senderName = senderEl ? (senderEl.textContent || '').trim().substring(0, 20) : '';" +

            // =========================================================================
            // FIX LỖI LẶP TIN: Dùng stableId cố định, không phụ thuộc vào đồng hồ TIME_
            // =========================================================================
            "           let stableId;" +
            "           if (realMsgId && realMsgId.length > 3 && !realMsgId.startsWith('TIME_')) {" +
            "               stableId = realMsgId;" +
            "           } else {" +
            "               let contentForHash = msgText.replace(/%%%[-0-9]+$/, '').trim();" +
            "               if (isVoice) {" +
            "                   let voiceTimeKey = (realMsgId && realMsgId.length > 3 && !realMsgId.startsWith('TIME_') && !realMsgId.startsWith('TS_')) ? realMsgId : ('V_' + convId + '_' + timeString + '_' + senderName);" +
			"                   stableId = 'VOICE_' + voiceTimeKey;" +
            "               } else {" +
            "                   stableId = 'CONTENT_' + convId + '_' + contentForHash.substring(0, 60);" +
            "               }" +
            "           }" +
            "           let fp = 'MSG|' + convId + '|' + stableId;" +

            "           if (!realMsgId || realMsgId === '') {" +
            "               realMsgId = 'TIME_' + timeString;" +
            "           }" +
            "           if(window.zauto_seen[fp]) return;" +
            "           window.zauto_seen[fp] = true;" +
            "           window.zauto_seen_keys.push(fp);" +
            "           if(window.zauto_seen_keys.length > 800) { " +
            "               let old = window.zauto_seen_keys.splice(0, 200); " +
            "               old.forEach(k => { delete window.zauto_seen[k]; });" + 
            "           }" +
            "           if (Date.now() - window.zauto_boot_time > 8000) {" +
            "               ZAutoBridge.onNewWebMsg(groupName, msgText, realMsgId, convId);" +
            "           }" +
            "       } catch(e) {}" +
            "   }" +
            "   window.scanConvItem = scanConvItem;" +
            // HÀM THU THẬP DANH SÁCH NHÓM
            "   function collectGroups() {" +
            "       try {" +
            "           let groups = [];" +
            "           let nameEls = document.querySelectorAll('.conv-item-title__name');" +
            "           nameEls.forEach(el => {" +
            "               let n = (el.innerText || el.textContent || '').trim();" +
            "               if(n && n.length > 1 && n.length < 80 && !groups.includes(n)) groups.push(n);" +
            "           });" +
            "           if(groups.length > 0) ZAutoBridge.onGroupListReceived(JSON.stringify(groups));" +
            "       } catch(e) {}" +
            "   }" +

            // OBSERVE CONTAINER SIDEBAR
            "   function startSidebarObserver() {" +
            "       let container = document.getElementById('conversationListId');" +
            "       if(!container) {" +
            "           setTimeout(startSidebarObserver, 1500);" +
            "           return;" +
            "       }" +
            "       if(window.zauto_sidebar_observer) window.zauto_sidebar_observer.disconnect();" +
            "       window.zauto_sidebar_observer = new MutationObserver(mutations => {" +
			"           mutations.forEach(m => {" +
			"               try {" +
			"                   let targetNode = m.target.nodeType === 3 ? m.target.parentNode : m.target;" +
			"                   let msgItem = targetNode.closest('.msg-item');" +
			"                   if(msgItem) scanConvItem(msgItem);" +
			"                   if (m.addedNodes && m.addedNodes.length > 0) {" +
			"                       m.addedNodes.forEach(nd2 => {" +
			"                           if (nd2.nodeType !== 1) return;" +
			"                           var isMsg = (nd2.id && (nd2.id.startsWith('msg')||nd2.id.startsWith('message-frame_'))) || nd2.hasAttribute('data-qid') ||" +
			"                                       nd2.classList.contains('msg-item') || nd2.querySelector('[data-qid],[id^=\"message-frame_\"],[id^=msg_],[id^=msg-]');" +
			"                           if (isMsg) {" +
			"                               let mi2 = nd2.closest('.msg-item') || nd2;" +
			"                               if (mi2) scanConvItem(mi2);" +
			"                           }" +
			"                       });" +
			"                   }" +
			"               } catch(e) {}" +
			"           });" +
			"       });" +
            "       window.zauto_sidebar_observer.observe(container, { childList: true, subtree: true, characterData: true });" +
            "       document.querySelectorAll('.msg-item').forEach(scanConvItem);" +
            "       collectGroups();" +
            "       ZAutoBridge.onLoginSuccess('Đã kết nối', '');" +
            "   }" +

            // WATCHDOG + NÚT ĐỒNG BỘ
            "   function systemWatchdog() {" +
            "       let imei = localStorage.getItem('z_uuid') || localStorage.getItem('sh_z_uuid') || '';" +
            "       ZAutoBridge.onHeartbeat(Date.now().toString(), imei);" +
            "       if(!navigator.onLine) { setTimeout(systemWatchdog, 10000); return; }" +
            "       try {" +
            "           let syncBtn = document.querySelector('.sync-msg-btn');" +
            "           if(!syncBtn) {" +
            "               let btns = document.querySelectorAll('button, div, span');" +
            "               for(let b of btns) { if(b.innerText && (b.innerText.includes('Đồng bộ') || b.innerText.includes('Khôi phục'))) { syncBtn = b; break; } }" +
            "           }" +
            "           if(syncBtn && !window.zauto_sync_clicked) { window.zauto_sync_clicked = true; syncBtn.click(); }" +
            "       } catch(e) {}" +
            "       let isLoginScreen = document.querySelector('.qrcode') || document.querySelector('.login-container');" +
			"       if(isLoginScreen) {" +
			"           if(!window.zauto_logout_notified) { window.zauto_logout_notified = true; ZAutoBridge.onLogout(); }" +
			"           if(!window.login_start_time) window.login_start_time = Date.now();" +
			"           if(Date.now() - window.login_start_time > 180000) { window.login_start_time = Date.now(); location.reload(); }" +
            "       } else {" +
			"           window.login_start_time = null;" +
			"           window.zauto_logout_notified = false;" +
            "           let container = document.getElementById('conversationListId');" +
            "           if(!container || !window.zauto_sidebar_observer) {" +
            "               window.zauto_sidebar_observer = null;" +
            "               startSidebarObserver();" +
            "           }" +
            "           window.zauto_group_tick = (window.zauto_group_tick || 0) + 1;" +
            "           if(window.zauto_group_tick % 5 === 0) collectGroups();" +
            "       }" +
            "       let nextTick = document.hidden ? 15000 : 3000;" +
            "       setTimeout(systemWatchdog, nextTick);" +
            "   }" +
            "   setInterval(() => { if(document.hidden) return; let container = document.getElementById('conversationListId'); if(container) document.querySelectorAll('.msg-item').forEach(scanConvItem); }, 2000);" +
            "   setTimeout(startSidebarObserver, 1000);" +
            "   setTimeout(systemWatchdog, 3000);" +
            "})();";

        safeEvaluateJs(js);
    }

    // =========================================================
    // JAVA WATCHDOG (kiểm tra heartbeat từ JS)
    // =========================================================
    private static void startWatchdog() {
        if (watchdogHandler == null) watchdogHandler = new Handler(Looper.getMainLooper());
        if (watchdogRunnable != null) watchdogHandler.removeCallbacks(watchdogRunnable);

        watchdogRunnable = new Runnable() {
            @Override
            public void run() {
                if (hiddenWebView != null) {
                    long now = System.currentTimeMillis();
                    if (now - lastHeartbeat > 60000) {
                        Log.e(TAG, "HEARTBEAT LOST. REQUESTING RELOAD...");
                        safeReload();
                    } else if (now - lastHeartbeat > 20000) {
                        safeEvaluateJs("if(!window.zauto_started) location.reload();");
                    }
                }
                watchdogHandler.postDelayed(this, 15000);
            }
        };
        watchdogHandler.postDelayed(watchdogRunnable, 15000);
    }

    // =========================================================
    // ĐIỀU CHỈNH TOẠ ĐỘ RENDER HIỂN THỊ WEB KHỚP VỚI CÁC TAB KIVY
    // =========================================================
    public static void updateWebViewBounds(
            final Activity activity,
            final int x, final int y,
            final int width, final int height,
            final boolean visible) {

        Activity safeActivity = activityRef != null ? activityRef.get() : activity;
        if (safeActivity == null) return;

        safeActivity.runOnUiThread(() -> {
            try {
                if (webLayout == null) return;
                FrameLayout.LayoutParams params =
                        (FrameLayout.LayoutParams) webLayout.getLayoutParams();
                if (!visible) {
                    webLayout.setAlpha(0.01f);
                    params.leftMargin = -2000;
                    params.topMargin = -2000;
                    params.width = 1080;
                    params.height = 2400;
                } else {
                    // TRẠNG THÁI HIỆN (TAB ZALO): Nổi lên trên đỉnh, hiển thị sắc nét đúng tọa độ Kivy chỉ định
                    webLayout.setAlpha(1.0f);
                    webLayout.setTranslationZ(100f);
                    params.leftMargin = x;
                    params.topMargin = y;
                    params.width = width;
                    params.height = height;
                    if (hiddenWebView != null) {
                        hiddenWebView.invalidate();
                        hiddenWebView.requestLayout();
                    }
                }
                webLayout.setLayoutParams(params);
            } catch (Exception e) {
                Log.e(TAG, "updateWebViewBounds Error", e);
            }
        });
    }
    // HÀM ĐỌC GIỌNG NÓI TỪ PYTHON GỌI XUỐNG
    public static void speak(String text) {
        if (tts != null) {
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, null);
        }
    }
    public static void reloadWeb(final Activity activity) {
        safeReload();
    }

    public static void onResume(final Activity activity) {
        Activity safeActivity = activityRef != null ? activityRef.get() : activity;
        if (safeActivity == null) return;
        safeActivity.runOnUiThread(() -> {
            try {
                if (hiddenWebView != null) hiddenWebView.onResume();
            } catch (Exception ignored) {}
        });
    }

    public static void onPause() {
        try {
            // ĐÃ XÓA LỆNH: hiddenWebView.onPause(); -> Để Javascript vẫn chạy khi app ẩn
        } catch (Exception ignored) {}
    }

    public static void destroy() {
        if (watchdogHandler != null && watchdogRunnable != null) {
            watchdogHandler.removeCallbacks(watchdogRunnable);
        }
        replyQueue.clear();
        if (webLayout != null) {
            webLayout.removeAllViews();
            webLayout = null;
        }
        if (hiddenWebView != null) {
            hiddenWebView.clearHistory();
            hiddenWebView.clearCache(true);
            hiddenWebView.destroy();
            hiddenWebView = null;
        }
        if (activityRef != null) {
            activityRef.clear();
            activityRef = null;
        }
    }

    // =========================================================
    // ẨN BÀN PHÍM CỨNG - GỌI TRƯỚC MỌI THAO TÁC CHỐT CUỐC
    // =========================================================
    public static void hideKeyboard(final Activity activity) {
        Activity safeActivity = activityRef != null ? activityRef.get() : activity;
        if (safeActivity == null) return;
        safeActivity.runOnUiThread(() -> {
            try {
                android.view.inputmethod.InputMethodManager imm =
                    (android.view.inputmethod.InputMethodManager)
                    safeActivity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE);
                android.view.View decorView = safeActivity.getWindow().getDecorView();
                android.os.IBinder token = decorView.getWindowToken();
                if (imm != null && token != null) {
                    imm.hideSoftInputFromWindow(token, 0);
                }
                if (hiddenWebView != null) {
                    hiddenWebView.evaluateJavascript(
                        "(function(){ try { var a = document.activeElement; if(a && a !== document.body) a.blur(); document.body.focus(); } catch(e){} })();", null);
                }
            } catch (Exception e) {}
        });
    }

    /// =========================================================
    // HỆ THỐNG PHÁT BẢN GHI ÂM CHUẨN XÁC THEO ID (ĐÃ SỬA LỖI NỐI CHUỖI)
    // =========================================================
    public static void playSpecificAudio(final Activity activity, final String conversationId, final String msgId) {
        Activity safeActivity = activityRef != null ? activityRef.get() : activity;
        if (safeActivity == null || hiddenWebView == null) return;

        safeActivity.runOnUiThread(() -> {
            String js = "(function() {" +
                "   let item = document.querySelector('.msg-item[anim-data-id=\"" + conversationId + "\"] .conv-item');" +
                "   if(item) {" +
                "       let key = Object.keys(item).find(k => k.startsWith('__reactEventHandlers') || k.startsWith('__reactFiber'));" +
                "       if (key && item[key]) {" +
                "           if (item[key].onClick) item[key].onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
                "           else if (item[key].return && item[key].return.memoizedProps.onClick) item[key].return.memoizedProps.onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
                "       } else { item.click(); }" +
                "   }" +
                "   setTimeout(() => {" +
                "       let findAndPlay = () => {" +
                "           let msgNode = document.querySelector('[data-msg-id=\"" + msgId + "\"]');" +
                "           if (!msgNode) msgNode = document.querySelector('div[id*=\"" + msgId + "\"]');" +
                "           if (!msgNode) {" +
                "               let allMsgs = document.querySelectorAll('.chat-item');" +
                "               if(allMsgs.length > 0) msgNode = allMsgs[allMsgs.length - 1];" +
                "           }" +
                "           if (!msgNode) return false;" +
                "           let playBtn = msgNode.querySelector('.fa-PlayCircle_24_Filled, [class*=\"PlayCircle\"], .v-audio, i[class*=\"play\"], div[class*=\"play-btn\"]');" +
                "           if(playBtn) {" +
                "               playBtn.click();" +
                "               let k = Object.keys(playBtn).find(key => key.startsWith('__reactEventHandlers') || key.startsWith('__reactFiber'));" +
                "               if(k && playBtn[k] && playBtn[k].onClick) playBtn[k].onClick({preventDefault:()=>{}, stopPropagation:()=>{}});" +
                "               return true;" +
                "           }" +
                "           return false;" +
                "       };" +
                "       if (!findAndPlay()) {" +
                "           let retryCount = 0;" +
                "           let interval = setInterval(() => {" +
                "               retryCount++;" +
                "               if (findAndPlay() || retryCount > 8) clearInterval(interval);" +
                "           }, 500);" +
                "       }" +
                "   }, 1500);" +
                "})();";
            hiddenWebView.evaluateJavascript(js, null);
        });
    }
	// =========================================================
    // HÀM HÚT COOKIE TỪ TRÌNH DUYỆT CHUYỂN CHO PYTHON
    // =========================================================
    public static String extractZaloCookie() {
        try {
            CookieManager cookieManager = CookieManager.getInstance();
            String cookie = cookieManager.getCookie("https://chat.zalo.me");
            return cookie != null ? cookie : "";
        } catch (Exception e) {
            Log.e(TAG, "Loi lay Cookie: ", e);
            return "";
        }
    }
	public static String getImei() {
        return currentImei;
    }

    public static String getUserAgent() {
        // Trả về đúng User-Agent mà ta đã gán cho WebView lúc khởi tạo
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36";
    }
}
