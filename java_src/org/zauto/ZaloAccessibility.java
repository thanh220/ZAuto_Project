package org.zauto;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.content.Intent;
import java.util.LinkedList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ZaloAccessibility extends AccessibilityService {

    public static ZaloAccessibility instance;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private static final String TAG = "ZAuto";
    private static final String ZALO_PACKAGE = "com.zing.zalo";

    // =====================================================
    // SERVICE CONNECT
    // =====================================================
    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        AccessibilityServiceInfo info = new AccessibilityServiceInfo();
        info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
                          AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED |
                          AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED |
                          AccessibilityEvent.TYPE_VIEW_SCROLLED |
                          AccessibilityEvent.TYPE_VIEW_CLICKED;
        info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
        info.packageNames = new String[]{ZALO_PACKAGE};
        info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
                     AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS |
                     AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS |
                     AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE;
        info.notificationTimeout = 50;
        setServiceInfo(info);
        Log.d(TAG, "Accessibility Connected");
    }

    // =====================================================
    // LISTEN EVENTS (Bắt thông báo Zalo)
    // =====================================================
    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        try {
            if (event == null || event.getPackageName() == null) return;
            String pkg = event.getPackageName().toString();
            if (!pkg.equals(ZALO_PACKAGE)) return;

            if (event.getEventType() == AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) {
                List<CharSequence> texts = event.getText();
                if (texts != null && !texts.isEmpty()) {
                    String full = texts.toString();
                    Log.d(TAG, "Notification: " + full);
                    try {
                        // Ném thông báo vào hàng đợi cho Python xử lý
                        if (ZaloWebManager.pythonMsgQueue.size() < 100) {
                            ZaloWebManager.pythonMsgQueue.add("WEB_NEW_MSG|||Zalo|||" + full + "||||||");
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Queue error: " + e.getMessage());
                    }
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "onAccessibilityEvent Error: " + e.getMessage());
        }
    }

    @Override
    public void onInterrupt() {
        Log.e(TAG, "Accessibility Interrupted");
    }

    @Override
    public boolean onUnbind(Intent intent) {
        instance = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        try { executor.shutdownNow(); } catch (Exception ignored) {}
        super.onDestroy();
    }

    // =====================================================
    // AUTO REPLY (Tự động lướt máy, bấm nút, gõ chữ)
    // =====================================================
    public void executeReplyContext(final String groupName, final String replyText) {
        executor.execute(() -> {
            AccessibilityNodeInfo root = null;
            try {
                Log.d(TAG, "START AUTO REPLY: " + groupName);
                root = waitForStableRoot(5000);
                if (root == null || root.getPackageName() == null) return;
                if (!root.getPackageName().toString().equals(ZALO_PACKAGE)) return;

                // 1. Tìm và Click vào Group Zalo
                AccessibilityNodeInfo groupNode = findNodeByTextContains(root, groupName);
                if (groupNode == null) return;
                AccessibilityNodeInfo clickable = getClickableParent(groupNode);
                if (clickable != null) {
                    clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sleep(1200);
                }
                recycleNode(groupNode);
                recycleNode(clickable);
                recycleNode(root);

                // 2. Tìm ô nhập Text và điền câu chốt cuốc
                root = waitForStableRoot(4000);
                if (root == null) return;
                AccessibilityNodeInfo inputBox = findInputBox(root);
                if (inputBox == null) return;
                
                Bundle args = new Bundle();
                args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, replyText);
                inputBox.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                sleep(500);

                // 3. Tìm nút Gửi và bấm
                AccessibilityNodeInfo sendBtn = findSendButton(root);
                if (sendBtn == null) return;
                sendBtn.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                sleep(800);

                // 4. Bấm phím Back để thoát ra ngoài chờ cuốc tiếp theo
                performGlobalAction(GLOBAL_ACTION_BACK);
                Log.d(TAG, "AUTO REPLY SUCCESS");

                recycleNode(inputBox);
                recycleNode(sendBtn);
            } catch (Exception e) {
                Log.e(TAG, "AUTO REPLY ERROR: " + e.getMessage());
            } finally {
                recycleNode(root);
            }
        });
    }

    // =====================================================
    // HELPER METHODS (Các hàm hỗ trợ tìm kiếm UI)
    // =====================================================
    private AccessibilityNodeInfo waitForStableRoot(int timeoutMs) {
        int waited = 0;
        while (waited < timeoutMs) {
            try {
                AccessibilityNodeInfo root = getRootInActiveWindow();
                if (root != null && root.getPackageName() != null && root.getChildCount() > 0) {
                    return AccessibilityNodeInfo.obtain(root);
                }
                Thread.sleep(200);
                waited += 200;
            } catch (Exception e) {
                Log.e(TAG, "waitRoot error: " + e.getMessage());
            }
        }
        return null;
    }

    private AccessibilityNodeInfo findNodeByTextContains(AccessibilityNodeInfo root, String target) {
        if (root == null) return null;
        Queue<AccessibilityNodeInfo> queue = new LinkedList<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            AccessibilityNodeInfo node = queue.poll();
            if (node == null) continue;
            try {
                CharSequence txt = node.getText();
                if (txt != null) {
                    if (txt.toString().toLowerCase().contains(target.toLowerCase())) {
                        return AccessibilityNodeInfo.obtain(node);
                    }
                }
                for (int i = 0; i < node.getChildCount(); i++) {
                    AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) queue.add(child);
                }
            } catch (Exception ignored) {}
        }
        return null;
    }

    private AccessibilityNodeInfo findInputBox(AccessibilityNodeInfo root) {
        if (root == null) return null;
        Queue<AccessibilityNodeInfo> queue = new LinkedList<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            AccessibilityNodeInfo node = queue.poll();
            if (node == null) continue;
            try {
                CharSequence cls = node.getClassName();
                if (cls != null && cls.toString().contains("EditText")) {
                    return AccessibilityNodeInfo.obtain(node);
                }
                for (int i = 0; i < node.getChildCount(); i++) {
                    AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) queue.add(child);
                }
            } catch (Exception ignored) {}
        }
        return null;
    }

    private AccessibilityNodeInfo findSendButton(AccessibilityNodeInfo root) {
        if (root == null) return null;
        Queue<AccessibilityNodeInfo> queue = new LinkedList<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            AccessibilityNodeInfo node = queue.poll();
            if (node == null) continue;
            try {
                CharSequence desc = node.getContentDescription();
                CharSequence txt = node.getText();
                if (desc != null) {
                    String d = desc.toString().toLowerCase();
                    if (d.contains("gửi") || d.contains("send")) return AccessibilityNodeInfo.obtain(node);
                }
                if (txt != null) {
                    String t = txt.toString().toLowerCase();
                    if (t.equals("gửi") || t.equals("send")) return AccessibilityNodeInfo.obtain(node);
                }
                for (int i = 0; i < node.getChildCount(); i++) {
                    AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) queue.add(child);
                }
            } catch (Exception ignored) {}
        }
        return null;
    }

    private AccessibilityNodeInfo getClickableParent(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo parent = node;
        for (int i = 0; i < 10; i++) {
            if (parent == null) return null;
            if (parent.isClickable()) return AccessibilityNodeInfo.obtain(parent);
            parent = parent.getParent();
        }
        return null;
    }

    private void recycleNode(AccessibilityNodeInfo node) {
        try { if (node != null) node.recycle(); } catch (Exception ignored) {}
    }

    private void sleep(long ms) {
        try { Thread.sleep(ms); } catch (Exception ignored) {}
    }
}
