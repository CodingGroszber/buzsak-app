package hu.buzsak.monitor;

import android.app.Notification;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
public class PendingAlertsTest {
    private Context context;
    private NotificationManager notifications;

    @Before
    public void prepare() {
        context = RuntimeEnvironment.getApplication();
        context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE)
            .edit().clear().commit();
        notifications = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        notifications.cancelAll();
    }

    private void post(String name) {
        assertTrue(PendingAlerts.post(context, name, "True", "Alerts", "Acknowledge"));
    }

    @Test
    public void eachFiringHasAnIndependentDurableIdentifier() {
        post("Heat");
        post("Heat");
        assertEquals(2, notifications.getActiveNotifications().length);
        assertEquals(10002, context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE)
            .getInt("next_id", -1));
    }

    @Test
    public void restoreRepostsPendingAlertsWithoutCreatingNewEntries() {
        post("Heat \ud83c\udf21");
        post("Rain");
        notifications.cancelAll();
        PendingAlerts.restore(context);
        PendingAlerts.restore(context);
        assertEquals(2, notifications.getActiveNotifications().length);
        assertEquals("Heat \ud83c\udf21", notifications.getActiveNotifications()[0]
            .getNotification().extras.getString(Notification.EXTRA_TITLE));
    }

    @Test
    public void alertsAreOngoingAndOpeningDoesNotAcknowledge() {
        post("Heat");
        Notification alert = notifications.getActiveNotifications()[0].getNotification();
        assertTrue((alert.flags & Notification.FLAG_ONGOING_EVENT) != 0);
        assertEquals(0, alert.flags & Notification.FLAG_AUTO_CANCEL);
        assertEquals("Acknowledge", alert.actions[0].title);
    }

    @Test
    public void acknowledgmentRemovesOnlyTheSelectedFiringAndSurvivesRestore() {
        post("Heat");
        post("Rain");
        Intent acknowledge = new Intent(PendingAlerts.ACKNOWLEDGE).putExtra("identifier", 10000);
        new AlertReceiver().onReceive(context, acknowledge);
        notifications.cancelAll();
        new AlertReceiver().onReceive(context, new Intent(Intent.ACTION_BOOT_COMPLETED));
        assertEquals(1, notifications.getActiveNotifications().length);
        assertEquals(10001, notifications.getActiveNotifications()[0].getId());
    }

    @Test
    public void acknowledgedIdentifiersAreNeverReused() {
        post("Heat");
        PendingAlerts.acknowledge(context, 10000);
        post("Rain");
        assertEquals(10001, notifications.getActiveNotifications()[0].getId());
    }

    @Test
    public void unrelatedBroadcastDoesNotAcknowledge() {
        post("Heat");
        new AlertReceiver().onReceive(context, new Intent("unrelated").putExtra("identifier", 10000));
        assertEquals(1, notifications.getActiveNotifications().length);
    }

    @Test
    public void deniedPermissionDoesNotCreateADeferredOccurrence() {
        org.robolectric.Shadows.shadowOf(notifications).setNotificationsEnabled(false);
        assertFalse(PendingAlerts.post(context, "Heat", "True", "Alerts", "Acknowledge"));
        assertTrue(context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE)
            .getAll().isEmpty());
        org.robolectric.Shadows.shadowOf(notifications).setNotificationsEnabled(true);
        PendingAlerts.restore(context);
        assertEquals(0, notifications.getActiveNotifications().length);
    }

    @Test
    public void taskRemovalAndEngineDetachKeepServiceAndAlertsAlive() {
        org.robolectric.util.ReflectionHelpers.setStaticField(MonitorPlugin.class, "context", context);
        MonitorService.running = false;
        MonitorService.requested = true;
        MonitorService service = org.robolectric.Robolectric.buildService(MonitorService.class)
            .create().get();
        try {
            service.onStartCommand(new Intent(), 0, 1);
            assertTrue(MonitorService.running);
            post("Heat");
            service.onTaskRemoved(new Intent());
            new MonitorPlugin().onDetachedFromEngine(null);
            assertTrue(MonitorService.running);
            assertEquals("active", MonitorService.reason);
            assertTrue(context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE)
                .contains("alert_10000"));
            service.onTimeout(1, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            assertFalse(MonitorService.running);
            assertEquals("timeout", MonitorService.reason);
            assertTrue(context.getSharedPreferences("buzsak_pending_alerts", Context.MODE_PRIVATE)
                .contains("alert_10000"));
        } finally {
            service.onDestroy();
            org.robolectric.util.ReflectionHelpers.setStaticField(MonitorPlugin.class, "context", null);
        }
    }
}