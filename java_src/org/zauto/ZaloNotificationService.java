package org.zauto;

import android.app.Notification;
import android.os.Build;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.text.TextUtils;
import android.util.Log;

public class ZaloNotificationService extends NotificationListenerService {

    private static final String TAG = "ZAutoNotif";
    private static final String ZALO_PACKAGE = "com.zing.zalo";

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        Log.d(TAG, "Notification Listener Connected");
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            // NULL CHECK CHỐNG CRASH VÀ CHỈ NHẬN THÔNG BÁO ZALO
            if (sbn == null || sbn.getPackageName() == null) return;
            if (!ZALO_PACKAGE.equals(sbn.getPackageName())) return;

            Notification notif = sbn.getNotification();
            if (notif == null) return;

            // BỎ QUA GROUP SUMMARY TRÁNH ĐỌC TRÙNG THÔNG BÁO
            if ((notif.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;

            Bundle extras = notif.extras;
            if (extras == null) return;

            // LẤY TIÊU ĐỀ (TÊN NHÓM) & NỘI DUNG CUỐC
            CharSequence titleSeq = extras.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence textSeq = extras.getCharSequence(Notification.EXTRA_TEXT);

            String group = titleSeq != null ? titleSeq.toString().trim() : "";
            String message = textSeq != null ? textSeq.toString().trim() : "";

            // CHỐNG MESSAGE RỖNG VÀ LOOP THÔNG BÁO HỆ THỐNG
            if (TextUtils.isEmpty(group) || TextUtils.isEmpty(message)) return;
            if (message.contains("tin nhắn mới")) return;

            // CHỐNG DUPLICATE (Tạo khóa nhận diện ID duy nhất)
            String notifKey;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
                notifKey = sbn.getKey();
            } else {
                notifKey = String.valueOf(System.currentTimeMillis());
            }

            // PUSH VÀO HÀNG ĐỢI RAM ĐỂ PYTHON XỬ LÝ (Kèm khóa an toàn chống tràn)
            String payload = "WEB_NEW_MSG|||" + group + "|||" + message + "|||" + notifKey + "|||NOTIFICATION";
            
            if (ZaloWebManager.pythonMsgQueue.size() < 100) {
                ZaloWebManager.pythonMsgQueue.add(payload);
            }

            Log.d(TAG, "NEW ZALO MSG => " + group + " | " + message);

        } catch (Exception e) {
            Log.e(TAG, "Notification Error: " + e.getMessage());
        }
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
        // Có thể dùng sau này nếu muốn sync trạng thái
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "Notification Listener Destroyed");
    }
}
