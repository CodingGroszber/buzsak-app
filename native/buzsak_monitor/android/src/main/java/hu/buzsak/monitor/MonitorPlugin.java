package hu.buzsak.monitor;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.embedding.engine.plugins.activity.ActivityAware;
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding;

public class MonitorPlugin implements FlutterPlugin, ActivityAware {
    private static Context context;
    private static Activity activity;
    private static String appName = "Buzsak";
    private static String monitoringText = "Monitoring active";
    private static String alertsChannel = "Custom alerts";
    private static String alertText = "Condition is true";
    private static String acknowledgeText = "Acknowledge";

    public void onAttachedToEngine(FlutterPluginBinding binding) {
        context = binding.getApplicationContext();
        PendingAlerts.restore(context);
    }
    public void onDetachedFromEngine(FlutterPluginBinding binding) { activity = null; }
    public void onAttachedToActivity(ActivityPluginBinding binding) { activity = binding.getActivity(); }
    public void onDetachedFromActivityForConfigChanges() { activity = null; }
    public void onReattachedToActivityForConfigChanges(ActivityPluginBinding binding) { activity = binding.getActivity(); }
    public void onDetachedFromActivity() { activity = null; }

    public static void configure(String name, String monitoring, String channel, String message,
                                 String acknowledge) {
        appName = name;
        monitoringText = monitoring;
        alertsChannel = channel;
        alertText = message;
        acknowledgeText = acknowledge;
    }

    private static NotificationManager manager() {
        return (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
    }

    static void createChannels() {
        if (Build.VERSION.SDK_INT >= 26) {
            manager().createNotificationChannel(new NotificationChannel(
                "buzsak_monitor", monitoringText, NotificationManager.IMPORTANCE_LOW));
            NotificationChannel alerts = new NotificationChannel(
                "buzsak_alerts", alertsChannel, NotificationManager.IMPORTANCE_DEFAULT);
            alerts.enableVibration(true);
            manager().createNotificationChannel(alerts);
        }
    }

    static Notification notification(String channel, String title, String text, boolean ongoing) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(context, channel) : new Notification.Builder(context);
        builder.setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title).setContentText(text).setOngoing(ongoing).setAutoCancel(!ongoing);
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        if (launch != null) {
            builder.setContentIntent(PendingIntent.getActivity(context, 0, launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        }
        if (!ongoing && Build.VERSION.SDK_INT < 26) builder.setDefaults(Notification.DEFAULT_ALL);
        return builder.build();
    }

    static Notification ongoingNotification() {
        return notification("buzsak_monitor", appName, monitoringText, true);
    }

    public static boolean start() {
        if (context == null || activity == null || activity.isFinishing()) return false;
        if (MonitorService.running) return true;
        createChannels();
        Intent intent = new Intent(context, MonitorService.class);
        try {
            MonitorService.requested = true;
            MonitorService.reason = "starting";
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
            else context.startService(intent);
            return true;
        } catch (RuntimeException error) {
            MonitorService.requested = false;
            MonitorService.reason = "unavailable";
            return false;
        }
    }

    public static void stop() {
        MonitorService.requested = false;
        MonitorService.running = false;
        MonitorService.reason = "stopped";
        if (context != null) context.stopService(new Intent(context, MonitorService.class));
    }

    public static String status() { return MonitorService.reason; }
    public static boolean active() { return MonitorService.running || MonitorService.requested; }
    public static boolean permissionGranted() {
        return context != null && (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(
            "android.permission.POST_NOTIFICATIONS") == PackageManager.PERMISSION_GRANTED)
            && manager().areNotificationsEnabled();
    }
    public static void requestPermission() {
        Activity current = activity;
        if (current != null && Build.VERSION.SDK_INT >= 33 && !permissionGranted()) {
            current.runOnUiThread(() -> current.requestPermissions(
                new String[]{"android.permission.POST_NOTIFICATIONS"}, 8421));
        }
    }
    public static boolean notifyAlert(int identifier, String title) {
        if (!permissionGranted()) return false;
        return PendingAlerts.post(context, title, alertText, alertsChannel, acknowledgeText);
    }
}