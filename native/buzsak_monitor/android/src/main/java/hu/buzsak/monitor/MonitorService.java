package hu.buzsak.monitor;

import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class MonitorService extends Service {
    public static volatile boolean running = false;
    public static volatile boolean requested = false;
    public static volatile String reason = "stopped";
    private PowerManager.WakeLock wakeLock;

    public IBinder onBind(Intent intent) { return null; }

    public int onStartCommand(Intent intent, int flags, int startId) {
        if (running) return START_NOT_STICKY;
        if (!requested) { stopSelf(); return START_NOT_STICKY; }
        try {
            MonitorPlugin.createChannels();
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(8419, MonitorPlugin.ongoingNotification(),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            } else startForeground(8419, MonitorPlugin.ongoingNotification());
            PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
            if (wakeLock == null) {
                wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "buzsak:monitor");
                wakeLock.acquire(6L * 60 * 60 * 1000);
            }
            running = true;
            requested = false;
            reason = "active";
        } catch (RuntimeException error) {
            requested = false;
            running = false;
            reason = "unavailable";
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    public void onTimeout(int startId, int foregroundServiceType) {
        reason = "timeout";
        requested = false;
        running = false;
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    public void onDestroy() {
        requested = false;
        running = false;
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        if ("active".equals(reason) || "starting".equals(reason)) reason = "stopped";
        super.onDestroy();
    }
}