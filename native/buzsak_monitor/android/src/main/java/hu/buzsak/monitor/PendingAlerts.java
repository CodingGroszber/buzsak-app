package hu.buzsak.monitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import org.json.JSONException;
import org.json.JSONObject;

final class PendingAlerts {
    private static final String CHANNEL = "buzsak_alerts";
    private static final String PREFIX = "alert_";
    static final String ACKNOWLEDGE = "hu.buzsak.monitor.ACKNOWLEDGE";

    private static SharedPreferences storage(Context context) {
        return context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE);
    }

    private static NotificationManager manager(Context context) {
        return (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
    }

    private static boolean allowed(Context context) {
        return (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(
            "android.permission.POST_NOTIFICATIONS") == PackageManager.PERMISSION_GRANTED)
            && manager(context).areNotificationsEnabled();
    }

    static synchronized boolean post(Context context, String name, String message,
                                     String channel, String acknowledge) {
        if (!allowed(context)) return false;
        SharedPreferences preferences = storage(context);
        int identifier = preferences.getInt("next_id", 10000);
        if (identifier == Integer.MAX_VALUE) return false;
        try {
            JSONObject alert = new JSONObject();
            alert.put("name", name);
            alert.put("message", message);
            alert.put("channel", channel);
            alert.put("acknowledge", acknowledge);
            alert.put("time", System.currentTimeMillis());
            if (!preferences.edit().putString(PREFIX + identifier, alert.toString())
                    .putInt("next_id", identifier + 1).commit()) return false;
            display(context, identifier, alert);
            return true;
        } catch (JSONException | RuntimeException error) {
            return false;
        }
    }

    private static void display(Context context, int identifier, JSONObject alert)
            throws JSONException {
        if (!allowed(context)) return;
        NotificationManager notifications = manager(context);
        if (Build.VERSION.SDK_INT >= 26) {
            notifications.createNotificationChannel(new NotificationChannel(
                CHANNEL, alert.getString("channel"), NotificationManager.IMPORTANCE_DEFAULT));
        }
        Intent acknowledge = new Intent(context, AlertReceiver.class)
            .setAction(ACKNOWLEDGE).putExtra("identifier", identifier);
        PendingIntent action = PendingIntent.getBroadcast(context, identifier, acknowledge,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(context, CHANNEL) : new Notification.Builder(context);
        builder.setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(alert.getString("name"))
            .setContentText(alert.getString("message"))
            .setWhen(alert.getLong("time"))
            .setOngoing(true).setAutoCancel(false).setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(null,
                alert.getString("acknowledge"), action).build());
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        if (launch != null) {
            builder.setContentIntent(PendingIntent.getActivity(context, identifier, launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        }
        if (Build.VERSION.SDK_INT < 26) builder.setDefaults(Notification.DEFAULT_ALL);
        notifications.notify(identifier, builder.build());
    }

    static synchronized void restore(Context context) {
        for (java.util.Map.Entry<String, ?> entry : storage(context).getAll().entrySet()) {
            if (!entry.getKey().startsWith(PREFIX)) continue;
            try {
                int identifier = Integer.parseInt(entry.getKey().substring(PREFIX.length()));
                display(context, identifier, new JSONObject((String) entry.getValue()));
            } catch (JSONException | RuntimeException error) {
                android.util.Log.w("BuzsakAlerts", "Pending alert could not be restored");
            }
        }
    }

    static synchronized void acknowledge(Context context, int identifier) {
        if (identifier < 10000) return;
        if (storage(context).edit().remove(PREFIX + identifier).commit()) {
            manager(context).cancel(identifier);
        }
    }
}