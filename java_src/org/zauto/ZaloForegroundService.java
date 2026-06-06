package org.zauto;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

public class ZaloForegroundService extends Service {

    private static final String TAG = "ZaloForegroundService";
    private static final String CHANNEL_ID = "zauto_channel";
    private static final int NOTIFICATION_ID = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        Notification notification = new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("ZAuto VIP")
                .setContentText("Đang chạy nền...")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .build();
        startForeground(NOTIFICATION_ID, notification);
        Log.d(TAG, "ZaloForegroundService started");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "ZaloForegroundService destroyed");
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "ZAuto Background Service",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Dịch vụ chạy nền ZAuto");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }
}
